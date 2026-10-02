import { Outlet, createRootRoute } from "@tanstack/react-router";
import { MotionConfig } from "motion/react";
import { NotFound } from "../components/NotFound";

export const Route = createRootRoute({
  component: () => (
    <MotionConfig reducedMotion="user">
      <Outlet />
    </MotionConfig>
  ),
  notFoundComponent: NotFound,
});
