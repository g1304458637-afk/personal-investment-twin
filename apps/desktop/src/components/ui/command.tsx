import { Command as CommandPrimitive } from "cmdk";
import { Search } from "lucide-react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

export const Command = forwardRef<
  React.ElementRef<typeof CommandPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive>
>(({ className, ...props }, ref) => (
  <CommandPrimitive
    ref={ref}
    className={cn("flex size-full flex-col overflow-hidden text-foreground", className)}
    {...props}
  />
));
Command.displayName = "Command";

export function CommandInput(props: React.ComponentPropsWithoutRef<typeof CommandPrimitive.Input>) {
  return (
    <div className="flex items-center border-b border-border px-3">
      <Search className="mr-2 size-4 shrink-0 text-muted" />
      <CommandPrimitive.Input
        className="flex h-12 w-full bg-transparent py-3 text-sm text-foreground outline-none placeholder:text-muted/65 disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      />
    </div>
  );
}

export const CommandList = forwardRef<
  React.ElementRef<typeof CommandPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.List>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.List ref={ref} className={cn("max-h-80 overflow-y-auto p-2", className)} {...props} />
));
CommandList.displayName = "CommandList";

export const CommandEmpty = CommandPrimitive.Empty;
export const CommandGroup = CommandPrimitive.Group;

export const CommandItem = forwardRef<
  React.ElementRef<typeof CommandPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Item>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Item
    ref={ref}
    className={cn(
      "flex cursor-default select-none items-center gap-3 rounded-md px-3 py-2.5 text-sm text-muted outline-none transition-colors data-[disabled=true]:pointer-events-none data-[selected=true]:bg-white/[0.07] data-[selected=true]:text-foreground data-[disabled=true]:opacity-45",
      className,
    )}
    {...props}
  />
));
CommandItem.displayName = "CommandItem";
