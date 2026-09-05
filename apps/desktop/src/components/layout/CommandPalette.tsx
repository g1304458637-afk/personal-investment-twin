import { CornerDownLeft } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useLocale } from "@/locales/LocaleProvider";

import { commandNavigationItems } from "./navigation";
import { isClassicWorkspace, workspaceDestinations } from "@/workspace/workspaceMode";
import { useWorkspaceCopy } from "@/workspace/copy";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const { t } = useLocale();
  const copy = useWorkspaceCopy();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onOpenChange, open]);

  const selectRoute = (path: string) => {
    navigate(path);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0">
        <DialogTitle className="sr-only">{t("Navigate the workspace")}</DialogTitle>
        <DialogDescription className="sr-only">
          {t("Search the available 投镜 workspace pages.")}
        </DialogDescription>
        <Command>
          <CommandInput autoFocus placeholder={t("Search workspace…")} />
          <CommandList>
            <CommandEmpty className="px-3 py-8 text-center text-sm text-muted">
              {t("No workspace page found.")}
            </CommandEmpty>
            <CommandGroup heading={t("Workspace")}>
              {!isClassicWorkspace() ? [...workspaceDestinations, {path:"/ask",label:"ask" as const}].map((item) => <CommandItem key={item.path} value={copy[item.label]} onSelect={() => selectRoute(item.path)}><div><strong>{copy[item.label]}</strong></div><CornerDownLeft className="ml-auto opacity-45" /></CommandItem>) : commandNavigationItems.map((item) => {
                const Icon = item.icon;
                return (
                  <CommandItem
                    key={item.path}
                    value={`${t(item.label)} ${t(item.description)}`}
                    onSelect={() => selectRoute(item.path)}
                  >
                    <Icon />
                    <div>
                      <strong>{t(item.label)}</strong>
                      <span>{t(item.description)}</span>
                    </div>
                    <CornerDownLeft className="ml-auto opacity-45" />
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
