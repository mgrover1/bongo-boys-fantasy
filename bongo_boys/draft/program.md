# Draft autoresearch program

Goal: maximise `score` from `prepare.evaluate` (mean simulated season lineup value of the
team drafted from slot 11 with Achane and DeVonta Smith kept), with `mean_rank` and `p_top3`
as tie-breakers.

Loop (one iteration):

1. Read `outputs/results.tsv` and `outputs/best_strategy.json` to see what has been tried.
2. Change ONE thing in `strategy.py` (a rule, or a PARAMS default). Never touch `prepare.py`.
3. `uv run bongo draft loop --desc "<what changed>" --seed 7` (same seed = common random numbers,
   so differences are comparable; 200 sims takes ~20 s).
4. `keep` means it beat the best so far and `best_strategy.json` was updated; otherwise revert
   the edit (`git checkout bongo_boys/draft/strategy.py`).
5. `uv run bongo draft loop --search 30 --seed 7` does the same for random perturbations of
   PARAMS without editing code.

Noise: score_std is ~200 per draft, so the standard error at 200 sims is ~14 points. Treat
improvements under ~15 as noise unless they repeat with `--seed 8`.

Ideas not yet tried: opponent-aware scarcity (count RB-needy teams before my next pick),
bye-week spreading, handcuff bonus for my own RB1, playoff-week (15-17) schedule tiebreak,
using the availability rollout from `live.py` inside the strategy instead of the ADP margin.
