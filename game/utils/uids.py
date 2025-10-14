import random
import time
import bittensor as bt
from game.api.get_query_axons import ping_uids
import numpy as np
from typing import List


async def get_random_uids(self, k: int, exclude: List[int] = None) -> np.ndarray:
    """Returns up to ``k`` available uids following selection-count and score rules."""

    exclude_set = {int(uid) for uid in (exclude or [])}

    successful_uids = await ping_uids(
        self.dendrite, self.metagraph, self.metagraph.uids, timeout=30
    )
    successful_set = {int(uid) for uid in successful_uids}

    window_seconds = self.scoring_window_seconds
    window_scores = {}
    selection_counts = {}
    min_selection_count = 0
    try:
        since = time.time() - float(window_seconds)
        window_scores = self.score_store.window_scores_by_hotkey(since)
        selection_counts = self.score_store.selection_counts_since(since)
        if selection_counts:
            min_selection_count = min(selection_counts.values())
        else:
            min_selection_count = 0
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to fetch window scores: {err}")
        window_scores = {}
        selection_counts = {}
        min_selection_count = 0

    print(
        f"Selection counts: {selection_counts}, min selection count: {min_selection_count}"
    )

    available_pool = [
        int(uid) for uid in self.metagraph.uids if int(uid) not in exclude_set
    ]

    random.shuffle(available_pool)
    selected: List[int] = []

    for uid in available_pool:
        if len(selected) >= k:
            break

        hotkey = self.metagraph.axons[uid].hotkey
        current_count = selection_counts.get(hotkey, min_selection_count)
        bt.logging.info(
            f"UID {uid} with {current_count} and min selection count {min_selection_count}"
        )

        if current_count > min_selection_count:
            continue

        try:
            self.score_store.increment_selection_count(hotkey, uid)
            selection_counts[hotkey] = current_count + 1
            if selection_counts:
                min_selection_count = min(
                    selection_counts.values()
                )  # Update min_selection_count
        except Exception as err:  # noqa: BLE001
            bt.logging.error(f"Failed to increment selection count for {hotkey}: {err}")

        if uid not in successful_set:
            continue

        score = float(window_scores.get(hotkey, 0.0))

        # Filter out very low score miners
        if score < -2.0:
            bt.logging.warning(f"UID {uid} has low score: {score}")
            continue

        selected.append(uid)

    if len(selected) < k:
        bt.logging.warning(
            f"Only selected {len(selected)} miners out of requested {k}."
        )
    else:
        bt.logging.info(
            f"Selected miners: {selected}, selected counts: {[selection_counts.get(self.metagraph.axons[uid].hotkey, 0) for uid in selected]}"
        )

    return np.array(selected, dtype=np.int32)
