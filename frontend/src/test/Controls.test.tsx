import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Controls } from "../components/Controls";

const baseProps = {
  status: "idle" as const,
  years: [],
  currentYear: null,
  isPlaying: false,
  speed: 1 as const,
  startYear: 2024,
  endYear: 2030,
  onStartStream: vi.fn(),
  onPlayPause: vi.fn(),
  onSpeedChange: vi.fn(),
  onScrub: vi.fn(),
  onStartYearChange: vi.fn(),
  onEndYearChange: vi.fn(),
};

describe("Controls", () => {
  it("renders Run button", () => {
    render(<Controls {...baseProps} />);
    expect(screen.getByText("Run")).toBeInTheDocument();
  });

  it("disables Run button while streaming", () => {
    render(<Controls {...baseProps} status="streaming" />);
    expect(screen.getByText("Streaming…")).toBeDisabled();
  });

  it("shows Play when not playing", () => {
    render(<Controls {...baseProps} years={[2024]} />);
    expect(screen.getByText("▶ Play")).toBeInTheDocument();
  });

  it("shows Pause when playing", () => {
    render(<Controls {...baseProps} years={[2024]} isPlaying={true} />);
    expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
  });

  it("calls onPlayPause when play clicked", () => {
    const onPlayPause = vi.fn();
    render(<Controls {...baseProps} years={[2024]} onPlayPause={onPlayPause} />);
    fireEvent.click(screen.getByText("▶ Play"));
    expect(onPlayPause).toHaveBeenCalledOnce();
  });

  it("calls onStartStream when Run clicked", () => {
    const onStartStream = vi.fn();
    render(<Controls {...baseProps} onStartStream={onStartStream} />);
    fireEvent.click(screen.getByText("Run"));
    expect(onStartStream).toHaveBeenCalledOnce();
  });

  it("calls onSpeedChange when speed button clicked", () => {
    const onSpeedChange = vi.fn();
    render(<Controls {...baseProps} onSpeedChange={onSpeedChange} />);
    fireEvent.click(screen.getByText("2×"));
    expect(onSpeedChange).toHaveBeenCalledWith(2);
  });

  it("highlights active speed button", () => {
    render(<Controls {...baseProps} speed={2} />);
    const btn = screen.getByText("2×");
    expect(btn).toHaveStyle({ background: "#e94560" });
  });

  it("shows current year in display", () => {
    render(<Controls {...baseProps} years={[2024]} currentYear={2024} />);
    expect(screen.getByText("2024")).toBeInTheDocument();
  });

  it("shows error message on error status", () => {
    render(<Controls {...baseProps} status="error" />);
    expect(screen.getByText("Stream error")).toBeInTheDocument();
  });
});
