"""Autoresearch loop: evaluate the current strategy, log it, keep the best.

uv run bongo draft loop --desc "what I changed"     # one evaluation, append results.tsv
uv run bongo draft loop --search 30                 # random search over PARAMS, keep best
"""

from __future__ import annotations

import json
import random
import subprocess
import time
from datetime import UTC, datetime

from bongo_boys.draft.context import BEST_PARAMS, OUTPUTS, load_params, load_setup
from bongo_boys.draft.prepare import evaluate
from bongo_boys.draft.strategy import PARAMS, make_strategy

RESULTS = OUTPUTS / "results.tsv"
HEADER = "commit\tscore\tscore_std\tmean_rank\tp_top3\tn_sims\tstatus\tdescription\n"
SEARCH_SCALE = 0.35  # relative perturbation of each numeric param


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"


def log_result(res: dict, status: str, desc: str) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    if not RESULTS.exists():
        RESULTS.write_text(HEADER)
    with RESULTS.open("a") as f:
        f.write(
            f"{git_hash()}\t{res['score']}\t{res['score_std']}\t{res['mean_rank']}\t{res['p_top3']}"
            f"\t{res['n_sims']}\t{status}\t{desc}\n"
        )


def best_score() -> float:
    if BEST_PARAMS.exists():
        return float(json.loads(BEST_PARAMS.read_text())["result"]["score"])
    return float("-inf")


def save_best(params: dict, res: dict, desc: str) -> None:
    BEST_PARAMS.write_text(
        json.dumps(
            {
                "params": params,
                "result": res,
                "description": desc,
                "saved_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
    )


def perturb(params: dict[str, float], rng: random.Random) -> dict[str, float]:
    out = {}
    for k, v in params.items():
        if k.endswith("_round") or k.startswith("depth_quota") or k.endswith("_from_end"):
            out[k] = max(1, int(round(v + rng.choice([-1, 0, 0, 1]))))
        else:
            out[k] = round(v * (1 + rng.gauss(0, SEARCH_SCALE)), 3)
    return out


def run(desc: str = "", search: int = 0, n_sims: int = 0, seed: int = 0) -> None:
    league, pool, state, setup = load_setup(picks_ttl=300)
    kw = {"n_sims": n_sims} if n_sims else {}
    if not search:
        params = load_params()
        res = evaluate(setup, make_strategy(params), seed=seed, **kw)
        status = "keep" if res["score"] > best_score() else "discard"
        if status == "keep":
            save_best(params, res, desc or "strategy.py edit")
        log_result(res, status, desc or "strategy.py edit")
        print(json.dumps({k: v for k, v in res.items() if k != "most_drafted"}, indent=2))
        print("most drafted:", res["most_drafted"][:10])
        print(status.upper(), "best:", best_score())
        return
    rng = random.Random(seed or int(time.time()))
    base = load_params()
    incumbent = evaluate(setup, make_strategy(base), seed=seed, **kw)
    if incumbent["score"] > best_score():
        save_best(base, incumbent, "incumbent")
    log_result(incumbent, "baseline", "search baseline")
    print("baseline", incumbent["score"], "+/-", incumbent["score_std"])
    for i in range(search):
        cand = perturb(load_params(), rng)
        res = evaluate(setup, make_strategy(cand), seed=seed, **kw)
        keep = res["score"] > best_score()
        if keep:
            save_best(cand, res, f"search iter {i}")
        changed = {k: v for k, v in cand.items() if v != base.get(k)}
        log_result(res, "keep" if keep else "discard", f"search {i}: " + json.dumps(changed)[:300])
        print(f"[{i}] {res['score']} ({'KEEP' if keep else 'discard'}) best={best_score()}")
    print("best params:", json.dumps(load_params(), indent=2))
    print("\nDefault PARAMS in strategy.py:", json.dumps(PARAMS))
