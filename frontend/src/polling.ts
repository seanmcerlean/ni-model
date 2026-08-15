import { LocationVotingPrediction, VotingPrediction } from "./types";

export type UndecidedAllocation = "reported" | "decided";
export type PollingShock = "neutral" | "brexit" | "anti_brexit";

export const BREXIT_SHOCK = 0.046;

interface PollShares {
  unite_share: number;
  remain_share: number;
  undecided_share: number;
}

export function allocateUndecided(
  prediction: PollShares,
  allocation: UndecidedAllocation,
): PollShares {
  if (allocation === "decided") {
    const decidedShare = prediction.unite_share + prediction.remain_share;
    if (decidedShare === 0) return prediction;
    return {
      unite_share: prediction.unite_share / decidedShare,
      remain_share: prediction.remain_share / decidedShare,
      undecided_share: 0,
    };
  }
  return prediction;
}

function shiftedShares<T extends PollShares>(prediction: T, amount: number): T {
  const actualShift = Math.max(
    -prediction.unite_share,
    Math.min(amount, prediction.remain_share),
  );
  return {
    ...prediction,
    unite_share: prediction.unite_share + actualShift,
    remain_share: prediction.remain_share - actualShift,
  };
}

function shockAmount(shock: PollingShock): number {
  if (shock === "brexit") return BREXIT_SHOCK;
  if (shock === "anti_brexit") return -BREXIT_SHOCK;
  return 0;
}

function adjustLocation(
  prediction: LocationVotingPrediction,
  amount: number,
): LocationVotingPrediction {
  const adjusted = shiftedShares(prediction, amount);
  const decided = adjusted.unite_share + adjusted.remain_share;
  return {
    ...adjusted,
    decided_unite_share: decided > 0 ? adjusted.unite_share / decided : 0,
    intervals: {
      ...prediction.intervals,
      unite_share: prediction.intervals.unite_share
        ? {
            low: Math.max(0, prediction.intervals.unite_share.low + amount),
            estimate: Math.max(0, Math.min(1, prediction.intervals.unite_share.estimate + amount)),
            high: Math.min(1, prediction.intervals.unite_share.high + amount),
          }
        : prediction.intervals.unite_share,
    },
    scenarios: prediction.scenarios.map((scenario) => ({
      ...scenario,
      unite_share: Math.max(0, Math.min(1, scenario.unite_share + amount)),
    })),
  };
}

export function applyPollingShock(
  prediction: VotingPrediction | null,
  shock: PollingShock,
): VotingPrediction | null {
  if (!prediction || shock === "neutral") return prediction;
  const amount = shockAmount(shock);
  return {
    ...adjustLocation(prediction, amount),
    source: prediction.source,
    limitations: prediction.limitations,
    by_location: prediction.by_location
      ? Object.fromEntries(
          Object.entries(prediction.by_location).map(([location, value]) => [
            location,
            adjustLocation(value, amount),
          ]),
        )
      : undefined,
  };
}
