export type UndecidedAllocation = "reported" | "remain" | "unite";

interface PollShares {
  unite_share: number;
  remain_share: number;
  undecided_share: number;
}

export function allocateUndecided(
  prediction: PollShares,
  allocation: UndecidedAllocation,
): PollShares {
  if (allocation === "unite") {
    return {
      unite_share: prediction.unite_share + prediction.undecided_share,
      remain_share: prediction.remain_share,
      undecided_share: 0,
    };
  }
  if (allocation === "remain") {
    return {
      unite_share: prediction.unite_share,
      remain_share: prediction.remain_share + prediction.undecided_share,
      undecided_share: 0,
    };
  }
  return prediction;
}
