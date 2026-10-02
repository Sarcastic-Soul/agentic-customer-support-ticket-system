import { createFileRoute } from "@tanstack/react-router";
import { MetricsPage } from "../pages/MetricsPage";

export const Route = createFileRoute("/admin/metrics")({
  component: MetricsPage,
});
