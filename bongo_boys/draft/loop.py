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


def best_score(n_sims: int = 0) -> float:
    """Best score so far; -inf if the best was measured with fewer sims than `n_sims`
    (results are only comparable at equal or greater sim counts)."""
    if BEST_PARAMS.exists():
        best = json.loads(BEST_PARAMS.read_text())["result"]
        if n_sims and int(best.get("n_sims", 0)) > n_sims:
            return float("inf")
        return float(best["score"])
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
            if k == "kdef_rounds_from_end":
                out[k] = min(out[k], 3)  # never burn a mid-round pick on K/DEF
        elif v == 0 and k in ("avail_sigma", "cliff_gap"):
            out[k] = round(rng.choice([0.0, 0.0, 6.0, 10.0, 15.0]), 3)  # sometimes switch on
        else:
            out[k] = round(abs(v) * (1 + rng.gauss(0, SEARCH_SCALE)), 3)  # params are magnitudes
            if k in ("wait_discount", "avail_strength"):
                out[k] = min(out[k], 1.0)
    return out


SCREEN_SIMS = 200  # stage 1: quick screen on seed 7
CONFIRM_SIMS = 400  # stage 2: confirm on seeds 8 and 9; combined score = mean of the three
CONFIRM_TOTAL = SCREEN_SIMS + 2 * CONFIRM_SIMS


def confirmed_eval(setup, params: dict[str, float]) -> tuple[dict, dict | None]:
    """Two-stage evaluation. Returns (screen_result, confirmed_result_or_None)."""
    r1 = evaluate(setup, make_strategy(params), n_sims=SCREEN_SIMS, seed=7)
    return r1, None


def confirm(setup, params: dict[str, float], r1: dict) -> dict:
    r2 = evaluate(setup, make_strategy(params), n_sims=CONFIRM_SIMS, seed=8)
    r3 = evaluate(setup, make_strategy(params), n_sims=CONFIRM_SIMS, seed=9)
    rs = [r1, r2, r3]
    w = [SCREEN_SIMS, CONFIRM_SIMS, CONFIRM_SIMS]
    tot = sum(w)
    out = {
        "score": round(sum(r["score"] * n for r, n in zip(rs, w, strict=True)) / tot, 1),
        "score_std": round(sum(r["score_std"] * n for r, n in zip(rs, w, strict=True)) / tot, 1),
        "mean_rank": round(sum(r["mean_rank"] * n for r, n in zip(rs, w, strict=True)) / tot, 2),
        "p_top3": round(sum(r["p_top3"] * n for r, n in zip(rs, w, strict=True)) / tot, 3),
        "n_sims": tot,
        "sample_roster": r2["sample_roster"],
        "most_drafted": r2["most_drafted"],
        "screen_score": r1["score"],
    }
    return out


def autoresearch(hours: float = 4.0, seed: int = 0) -> None:
    """Hill-climb PARAMS indefinitely: perturb best, screen at 200 sims, confirm at 1000."""
    league, pool, state, setup = load_setup(picks_ttl=300)
    rng = random.Random(seed or int(time.time()))
    deadline = time.time() + hours * 3600
    base = load_params()
    if best_score(CONFIRM_TOTAL) in (float("-inf"), float("inf")) or (
        BEST_PARAMS.exists()
        and json.loads(BEST_PARAMS.read_text())["result"].get("n_sims") != CONFIRM_TOTAL
    ):
        r1, _ = confirmed_eval(setup, base)
        res = confirm(setup, base, r1)
        save_best(base, res, "autoresearch incumbent")
        log_result(res, "baseline", "autoresearch incumbent")
        print("incumbent", res["score"], flush=True)
    i = 0
    screen_margin = 8.0  # candidates within this of the best screen score get confirmed
    while time.time() < deadline:
        best = json.loads(BEST_PARAMS.read_text())
        cur = best["params"]
        scale = rng.choice([0.15, 0.35, 0.35, 0.7])
        global SEARCH_SCALE
        SEARCH_SCALE = scale
        cand = perturb(cur, rng)
        changed = {k: v for k, v in cand.items() if v != cur.get(k)}
        r1, _ = confirmed_eval(setup, cand)
        best_screen = best["result"].get("screen_score", best["result"]["score"])
        if r1["score"] < best_screen - screen_margin:
            log_result(r1, "discard", f"auto {i} screen: " + json.dumps(changed)[:250])
            print(
                f"[{i}] screen {r1['score']} < {best_screen}-{screen_margin} (scale {scale})",
                flush=True,
            )
            i += 1
            continue
        res = confirm(setup, cand, r1)
        keep = res["score"] > best["result"]["score"]
        if keep:
            save_best(cand, res, f"autoresearch {i}")
        log_result(
            res, "keep" if keep else "discard", f"auto {i} confirmed: " + json.dumps(changed)[:250]
        )
        print(
            f"[{i}] confirmed {res['score']} ({'KEEP' if keep else 'discard'}) best={max(res['score'], best['result']['score'])} scale {scale}",
            flush=True,
        )
        i += 1
    print("done; best:", json.dumps(load_params()))


def run(desc: str = "", search: int = 0, n_sims: int = 0, seed: int = 0) -> None:
    league, pool, state, setup = load_setup(picks_ttl=300)
    kw = {"n_sims": n_sims} if n_sims else {}
    if not search:
        params = load_params()
        res = evaluate(setup, make_strategy(params), seed=seed, **kw)
        status = "keep" if res["score"] > best_score(res["n_sims"]) else "discard"
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
    if incumbent["score"] > best_score(incumbent["n_sims"]):
        save_best(base, incumbent, "incumbent")
    log_result(incumbent, "baseline", "search baseline")
    print("baseline", incumbent["score"], "+/-", incumbent["score_std"])
    for i in range(search):
        cand = perturb(load_params(), rng)
        res = evaluate(setup, make_strategy(cand), seed=seed, **kw)
        keep = res["score"] > best_score(res["n_sims"])
        if keep:
            save_best(cand, res, f"search iter {i}")
        changed = {k: v for k, v in cand.items() if v != base.get(k)}
        log_result(res, "keep" if keep else "discard", f"search {i}: " + json.dumps(changed)[:300])
        print(f"[{i}] {res['score']} ({'KEEP' if keep else 'discard'}) best={best_score()}")
    print("best params:", json.dumps(load_params(), indent=2))
    print("\nDefault PARAMS in strategy.py:", json.dumps(PARAMS))
