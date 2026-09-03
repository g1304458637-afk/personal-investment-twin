import type { ReactNode } from "react";

import { DemoBadge } from "./StatusBadge";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  showDemo = true,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  showDemo?: boolean;
}) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        <div className="page-header__eyebrow">
          <span>{eyebrow}</span>
          {showDemo ? <DemoBadge compact /> : null}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow ? <span className="section-heading__eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}
