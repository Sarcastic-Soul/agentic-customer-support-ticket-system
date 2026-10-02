import { createFileRoute } from "@tanstack/react-router";
import { KBPage } from "../pages/KBPage";

export const Route = createFileRoute("/admin/kb")({
  component: KBPage,
});
