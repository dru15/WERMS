import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { OperationsMap } from "./OperationsMap";

test("zoom controls change the map viewport", () => {
  const { container } = render(<OperationsMap />);
  const before = container.querySelector("svg.operations-map")?.getAttribute("viewBox");
  fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
  expect(container.querySelector("svg.operations-map")?.getAttribute("viewBox")).not.toBe(before);
});
