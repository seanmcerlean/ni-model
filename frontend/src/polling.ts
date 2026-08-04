export type UndecidedAllocation = "reported" | "decided";

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
