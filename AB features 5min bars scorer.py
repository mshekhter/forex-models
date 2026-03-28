# Train frozen A+B admission scorers on hard-negative samples and write the
# resulting scores back to df_model.
#
# Purpose:
# Fit one regularized linear admission model for long entries and one for short
# entries, using only Family A and Family B side-native features.
# The target is the frozen retained episode entry label on the df5 bar index.
#
# Label definition:
# y_long and y_short are sparse entry-bar labels only.
# They mark where retained long and short episodes begin.
# They are not bar-by-bar trade outcome labels.
#
# Feature scope:
# The long model uses only A+B up-side columns.
# The short model uses only A+B down-side columns.
# No cross-side feature mixing is used here.
#
# Sample design:
# Training and test are evaluated on hard-negative samples, not all non-entry
# bars.
# Negatives are drawn from bars outside a blocked buffer around any retained
# entry, then matched by calendar year to the positive sample at a fixed 10:1
# negative-to-positive ratio.
#
# Model form:
# Each side uses the same pipeline:
# median imputation,
# standard scaling,
# L2-regularized logistic regression with balanced class weights.
#
# Scoring output:
# The fitted models produce raw probability scores for every row in df_model.
# Each raw score is also converted into a percentile rank against that model's
# train-score distribution.
#
# Written outputs:
# This cell writes four score columns into df_model:
# score_long_ab
# score_short_ab
# score_long_ab_pct
# score_short_ab_pct
#
# Frozen artifacts:
# The fitted models, feature lists, score column names, split date, and full
# preprocessing and coefficient details are saved into named artifacts for
# later scoring and replay use.

import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score

# Require the modeling frame that will receive the score columns,
# the master 5 minute bar frame used for label alignment,
# and the retained episode table that defines entry timestamps and sides.
if "df_model" not in globals():
    raise NameError("df_model is not defined")
if "df5" not in globals():
    raise NameError("df5 is not defined")
if "episodes_df" not in globals():
    raise NameError("episodes_df is not defined")

# Frozen global settings for split date and hard-negative construction.
TRAIN_END = pd.Timestamp("2024-06-30 23:59:59+00:00")
BUFFER = 24
NEG_PER_POS = 10
RNG_SEED = 42

# Start from df_model, normalize timestamps, and extract calendar year for
# year-matched negative sampling.
df_eval = df_model.copy()
df_eval["timestamp"] = pd.to_datetime(df_eval["timestamp"], utc=True, errors="raise")
df_eval["year"] = df_eval["timestamp"].dt.year.astype(int)

# Map retained episode entry timestamps back to exact df5 row positions.
ts5 = pd.to_datetime(df5["timestamp"], utc=True, errors="raise")
ts5_index = pd.Index(ts5)

entry_t = pd.to_datetime(episodes_df["entry_t"], utc=True, errors="raise")
entry_i = ts5_index.get_indexer(entry_t)
if (entry_i < 0).any():
    raise ValueError("Some episode entry_t values could not be mapped to df5")

# Require row-for-row alignment between df_model and df5 before labels are added.
if len(df_eval) != len(df5):
    raise ValueError(f"Length mismatch: len(df_model)={len(df_eval)} vs len(df5)={len(df5)}")

# Build side-specific sparse entry labels on the df5 index.
# A value of 1 marks an entry bar for that side.
# All other bars remain 0.
y_long = np.zeros(len(df5), dtype=np.int8)
y_short = np.zeros(len(df5), dtype=np.int8)
ep_side = episodes_df["side"].astype(str).to_numpy()

y_long[entry_i[ep_side == "long"]] = 1
y_short[entry_i[ep_side == "short"]] = 1

# Attach frozen labels to the evaluation frame.
df_eval["y_long"] = y_long
df_eval["y_short"] = y_short

# Select exact A+B side-native feature sets.
# Long uses only up-native Family A and Family B columns.
AB_long_cols = sorted([
    c for c in df_eval.columns
    if (c.startswith("famA_") or c.startswith("famB_")) and ("_up_" in c or c.endswith("_up"))
])

# Short uses only down-native Family A and Family B columns.
AB_short_cols = sorted([
    c for c in df_eval.columns
    if (c.startswith("famA_") or c.startswith("famB_")) and ("_dn_" in c or c.endswith("_dn"))
])

if len(AB_long_cols) == 0:
    raise ValueError("No A+B long-native columns found in df_model")
if len(AB_short_cols) == 0:
    raise ValueError("No A+B short-native columns found in df_model")

# Global time-based split used throughout model fitting and evaluation.
train_mask_all = (df_eval["timestamp"] <= TRAIN_END).to_numpy()
test_mask_all = (df_eval["timestamp"] > TRAIN_END).to_numpy()

# Block a symmetric window around every retained entry.
# Bars inside blocked regions cannot be sampled as negatives.
blocked = np.zeros(len(df_eval), dtype=bool)
for idx in entry_i:
    lo = max(0, idx - BUFFER)
    hi = min(len(df_eval), idx + BUFFER + 1)
    blocked[lo:hi] = True

# Build one hard-negative sample mask for a given side and split.
# Positives are all labeled entry bars for that side inside the split.
# Negatives come from non-entry bars inside the split and outside blocked zones.
# Sampling is done year by year to roughly preserve the positive year mix.
# Within each year, sample up to NEG_PER_POS negatives per positive.
def build_hard_sample_mask(y_col, split_mask, rng_seed):
    rng = np.random.default_rng(rng_seed)

    y_arr = df_eval[y_col].to_numpy(dtype=np.int8)
    year_arr = df_eval["year"].to_numpy(dtype=np.int64)

    pos_idx = np.flatnonzero((y_arr == 1) & split_mask)
    neg_pool_idx = np.flatnonzero((y_arr == 0) & split_mask & (~blocked))

    neg_by_year = {}
    for yr in np.unique(year_arr[neg_pool_idx]):
        neg_by_year[int(yr)] = neg_pool_idx[year_arr[neg_pool_idx] == yr].copy()

    pos_year_counts = pd.Series(year_arr[pos_idx]).value_counts().sort_index()

    chosen_neg = []
    for yr, pos_count in pos_year_counts.items():
        yr = int(yr)
        need = int(pos_count) * NEG_PER_POS
        pool = neg_by_year.get(yr, np.array([], dtype=np.int64))
        if len(pool) == 0:
            continue
        if len(pool) <= need:
            picked = pool.copy()
        else:
            picked = np.sort(rng.choice(pool, size=need, replace=False))
        chosen_neg.append(picked)

    neg_idx = np.concatenate(chosen_neg) if len(chosen_neg) > 0 else np.array([], dtype=np.int64)

    sample_mask = np.zeros(len(df_eval), dtype=bool)
    sample_mask[pos_idx] = True
    sample_mask[neg_idx] = True

    return sample_mask, pos_idx, neg_idx

# Build separate hard-negative train and test samples for long and short.
# Different seeds keep the draws reproducible while avoiding identical samples.
train_sample_long, train_pos_long, train_neg_long = build_hard_sample_mask("y_long", train_mask_all, RNG_SEED + 101)
test_sample_long,  test_pos_long,  test_neg_long  = build_hard_sample_mask("y_long", test_mask_all,  RNG_SEED + 102)

train_sample_short, train_pos_short, train_neg_short = build_hard_sample_mask("y_short", train_mask_all, RNG_SEED + 201)
test_sample_short,  test_pos_short,  test_neg_short  = build_hard_sample_mask("y_short", test_mask_all,  RNG_SEED + 202)

# Safe AUC wrapper for binary labels and numeric scores.
# Returns NaN when the sample is empty or contains only one class.
def auc_safe(y_true, score):
    y_true = np.asarray(y_true, dtype=np.int8)
    score = np.asarray(score, dtype=float)
    ok = np.isfinite(score)
    y_true = y_true[ok]
    score = score[ok]
    if len(y_true) == 0:
        return np.nan
    if y_true.min() == y_true.max():
        return np.nan
    return float(roc_auc_score(y_true, score))

# Summarize how concentrated positives are in the highest-score tail.
# frac defines the top fraction to inspect, such as 10 percent or 5 percent.
# Returns sample size, cutoff count, base rate, precision, lift, and threshold.
def top_tail_stats(y_true, score, frac):
    y_true = np.asarray(y_true, dtype=np.int8)
    score = np.asarray(score, dtype=float)

    ok = np.isfinite(score)
    y_true = y_true[ok]
    score = score[ok]

    n = len(y_true)
    if n == 0:
        return {
            "n_total": 0,
            "k": 0,
            "base_rate": np.nan,
            "precision": np.nan,
            "lift": np.nan,
            "threshold": np.nan,
        }

    k = max(1, int(np.ceil(frac * n)))
    order = np.argsort(-score, kind="mergesort")
    top_idx = order[:k]

    base_rate = float(y_true.mean())
    precision = float(y_true[top_idx].mean())
    lift = np.nan if base_rate <= 0 else float(precision / base_rate)
    threshold = float(score[top_idx[-1]])

    return {
        "n_total": int(n),
        "k": int(k),
        "base_rate": base_rate,
        "precision": precision,
        "lift": lift,
        "threshold": threshold,
    }

# Convert raw scores into percentile ranks using the train-score distribution
# as the frozen reference set.
def percentile_rank_from_train(train_s, score_s):
    train_s = np.asarray(train_s, dtype=float)
    score_s = np.asarray(score_s, dtype=float)

    train_ok = np.isfinite(train_s)
    ref = np.sort(train_s[train_ok])

    out = np.full(len(score_s), np.nan, dtype=float)
    if len(ref) == 0:
        return out

    score_ok = np.isfinite(score_s)
    out[score_ok] = np.searchsorted(ref, score_s[score_ok], side="right") / len(ref)
    return out

# Fit one regularized linear admission model for one side and one label.
# Workflow:
# 1. subset train and test to the prebuilt hard-negative sample masks
# 2. fit the preprocessing + logistic regression pipeline on train
# 3. score train, test, and all rows
# 4. convert all-row scores into train-based percentile ranks
# 5. collect metrics, coefficient details, and frozen scoring artifacts
def fit_regularized_linear_and_score(feature_cols, y_col, train_sample_mask, test_sample_mask, score_col):
    X_train = df_eval.loc[train_sample_mask, feature_cols].copy()
    y_train = df_eval.loc[train_sample_mask, y_col].astype(np.int8).copy()

    X_test = df_eval.loc[test_sample_mask, feature_cols].copy()
    y_test = df_eval.loc[test_sample_mask, y_col].astype(np.int8).copy()

    X_all = df_eval.loc[:, feature_cols].copy()

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            penalty="l2",
            C=1.0,
            solver="lbfgs",
            max_iter=2000,
            class_weight="balanced",
            random_state=42,
        )),
    ])

    pipe.fit(X_train, y_train)

    # Raw model scores are class-1 probabilities.
    train_score = pipe.predict_proba(X_train)[:, 1]
    test_score = pipe.predict_proba(X_test)[:, 1]
    all_score = pipe.predict_proba(X_all)[:, 1]

    # Percentile column is defined relative to the train-score distribution only.
    pct_col = score_col + "_pct"
    all_pct = percentile_rank_from_train(train_score, all_score)

    # Write full-row raw scores and percentile scores into the working frame.
    df_eval[score_col] = all_score
    df_eval[pct_col] = all_pct

    # Evaluate the highest-score tails on test.
    dec = top_tail_stats(y_test.to_numpy(dtype=np.int8), test_score, 0.10)
    ven = top_tail_stats(y_test.to_numpy(dtype=np.int8), test_score, 0.05)

    # For test positives only, summarize where they land in train-based percentile space.
    test_pct = percentile_rank_from_train(train_score, test_score)
    pos_test_pct = test_pct[y_test.to_numpy(dtype=np.int8) == 1]

    # Compact model summary for reporting.
    metrics = pd.DataFrame([{
        "label": y_col,
        "model": "regularized_linear",
        "train_rows": int(len(X_train)),
        "train_pos": int(y_train.sum()),
        "train_neg": int((y_train == 0).sum()),
        "test_rows": int(len(X_test)),
        "test_pos": int(y_test.sum()),
        "test_neg": int((y_test == 0).sum()),
        "train_auc": auc_safe(y_train.to_numpy(dtype=np.int8), train_score),
        "test_auc": auc_safe(y_test.to_numpy(dtype=np.int8), test_score),
        "test_top_decile_k": dec["k"],
        "test_top_decile_precision": dec["precision"],
        "test_top_decile_lift": dec["lift"],
        "test_top_ventile_k": ven["k"],
        "test_top_ventile_precision": ven["precision"],
        "test_top_ventile_lift": ven["lift"],
        "test_pos_pct_p10": float(np.nanquantile(pos_test_pct, 0.10)) if len(pos_test_pct) else np.nan,
        "test_pos_pct_p25": float(np.nanquantile(pos_test_pct, 0.25)) if len(pos_test_pct) else np.nan,
        "test_pos_pct_p50": float(np.nanquantile(pos_test_pct, 0.50)) if len(pos_test_pct) else np.nan,
        "test_pos_pct_p75": float(np.nanquantile(pos_test_pct, 0.75)) if len(pos_test_pct) else np.nan,
        "test_pos_pct_p90": float(np.nanquantile(pos_test_pct, 0.90)) if len(pos_test_pct) else np.nan,
    }])

    # Freeze preprocessing and model details needed for later reuse.
    imputer = pipe.named_steps["imputer"]
    scaler = pipe.named_steps["scaler"]
    clf = pipe.named_steps["clf"]

    artifact = {
        "label": y_col,
        "model_name": "regularized_linear",
        "feature_cols": list(feature_cols),
        "score_col": score_col,
        "score_pct_col": pct_col,
        "train_end": TRAIN_END,
        "buffer": BUFFER,
        "neg_per_pos": NEG_PER_POS,
        "rng_seed": RNG_SEED,
        "train_sample_rows": int(train_sample_mask.sum()),
        "test_sample_rows": int(test_sample_mask.sum()),
        "imputer_statistics_": pd.Series(imputer.statistics_, index=feature_cols, dtype=float),
        "scaler_mean_": pd.Series(scaler.mean_, index=feature_cols, dtype=float),
        "scaler_scale_": pd.Series(scaler.scale_, index=feature_cols, dtype=float),
        "intercept_": float(clf.intercept_[0]),
        "coef_": pd.Series(clf.coef_[0], index=feature_cols, dtype=float),
        "train_score_reference": pd.Series(train_score, name=score_col, dtype=float),
    }

    # Coefficient detail table ranked by absolute magnitude for quick inspection.
    coef_detail = (
        pd.DataFrame({
            "feature": feature_cols,
            "coef": clf.coef_[0],
            "abs_coef": np.abs(clf.coef_[0]),
        })
        .sort_values(["abs_coef", "feature"], ascending=[False, True], kind="mergesort")
        .reset_index(drop=True)
    )

    return {
        "pipe": pipe,
        "artifact": artifact,
        "metrics": metrics,
        "coef_detail": coef_detail,
    }

# Fit the long admission scorer on long labels and A+B up-side features.
long_fit = fit_regularized_linear_and_score(
    feature_cols=AB_long_cols,
    y_col="y_long",
    train_sample_mask=train_sample_long,
    test_sample_mask=test_sample_long,
    score_col="score_long_ab",
)

# Fit the short admission scorer on short labels and A+B down-side features.
short_fit = fit_regularized_linear_and_score(
    feature_cols=AB_short_cols,
    y_col="y_short",
    train_sample_mask=train_sample_short,
    test_sample_mask=test_sample_short,
    score_col="score_short_ab",
)

# Write the fitted score outputs back into df_model.
df_model["score_long_ab"] = df_eval["score_long_ab"].to_numpy(dtype=float)
df_model["score_short_ab"] = df_eval["score_short_ab"].to_numpy(dtype=float)
df_model["score_long_ab_pct"] = df_eval["score_long_ab_pct"].to_numpy(dtype=float)
df_model["score_short_ab_pct"] = df_eval["score_short_ab_pct"].to_numpy(dtype=float)

# Expose the fitted pipelines under frozen names for later use.
admit_model_long = long_fit["pipe"]
admit_model_short = short_fit["pipe"]

# Expose frozen artifacts for later scoring and replay use.
admit_artifact_long = long_fit["artifact"]
admit_artifact_short = short_fit["artifact"]

# Freeze the exact feature lists used to fit each side.
admit_feature_cols_long = list(AB_long_cols)
admit_feature_cols_short = list(AB_short_cols)

# Freeze score column naming so later code can refer to them consistently.
admit_score_cols = {
    "long": "score_long_ab",
    "short": "score_short_ab",
    "long_pct": "score_long_ab_pct",
    "short_pct": "score_short_ab_pct",
}

# Freeze the train/test cutoff date used for these scorers.
admit_train_split_date = TRAIN_END

# Print compact fitting and scoring summaries.
print("A+B long cols :", len(AB_long_cols))
print("A+B short cols:", len(AB_short_cols))
print("long hard negatives train/test :", len(train_neg_long), len(test_neg_long))
print("short hard negatives train/test:", len(train_neg_short), len(test_neg_short))

print("\nAdmission scorer test metrics")
print(pd.concat([long_fit["metrics"], short_fit["metrics"]], ignore_index=True).to_string(index=False))

print("\nLong regularized linear top coefficients")
print(long_fit["coef_detail"].head(30).to_string(index=False))

print("\nShort regularized linear top coefficients")
print(short_fit["coef_detail"].head(30).to_string(index=False))

print("\nScore columns written to df_model:")
print(["score_long_ab", "score_short_ab", "score_long_ab_pct", "score_short_ab_pct"])

print("\nFrozen artifacts:")
print("admit_model_long")
print("admit_model_short")
print("admit_artifact_long")
print("admit_artifact_short")
print("admit_feature_cols_long")
print("admit_feature_cols_short")
print("admit_score_cols")
print("admit_train_split_date")