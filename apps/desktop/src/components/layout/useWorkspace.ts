import { useOutletContext } from "react-router-dom";

export interface WorkspaceActions {
  openAgent: () => void;
}

export function useWorkspace() {
  return useOutletContext<WorkspaceActions>();
}
