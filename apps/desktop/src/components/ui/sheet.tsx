import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;
export const SheetTitle = DialogPrimitive.Title;
export const SheetDescription = DialogPrimitive.Description;

export const SheetContent = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  const { t } = useLocale();
  return <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[#04070d]/54 backdrop-blur-[4px] data-[state=closed]:animate-[mirror-fade-out_160ms_ease_forwards] data-[state=open]:animate-[mirror-fade-in_180ms_ease_forwards]" />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed inset-y-0 right-0 z-50 w-[min(92vw,520px)] overflow-y-auto border-l border-white/10 bg-[hsl(var(--overlay))]/95 p-6 text-foreground shadow-[-20px_0_80px_rgba(0,0,0,.34)] outline-none backdrop-blur-3xl data-[state=closed]:animate-[mirror-sheet-out_220ms_var(--ease-mirror)_forwards] data-[state=open]:animate-[mirror-sheet-in_320ms_var(--ease-mirror)_forwards]",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-5 top-5 inline-flex size-8 items-center justify-center rounded-md text-muted outline-none transition-colors hover:bg-white/[0.07] hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/55">
        <X className="size-4" />
        <span className="sr-only">{t("Close panel")}</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>;
});
SheetContent.displayName = "SheetContent";
