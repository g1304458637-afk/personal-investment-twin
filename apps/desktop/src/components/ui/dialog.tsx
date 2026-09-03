import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;

export const DialogContent = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  const { t } = useLocale();
  return <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[#04070d]/58 backdrop-blur-[5px] data-[state=closed]:animate-[mirror-fade-out_160ms_ease_forwards] data-[state=open]:animate-[mirror-fade-in_180ms_ease_forwards]" />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 w-[min(92vw,600px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-[hsl(var(--overlay))]/94 p-6 text-foreground shadow-float outline-none backdrop-blur-3xl data-[state=closed]:animate-[mirror-dialog-out_180ms_ease_forwards] data-[state=open]:animate-[mirror-dialog-in_260ms_var(--ease-mirror)_forwards]",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-md text-muted outline-none transition-colors hover:bg-white/[0.07] hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/55">
        <X className="size-4" />
        <span className="sr-only">{t("Close")}</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>;
});
DialogContent.displayName = "DialogContent";
