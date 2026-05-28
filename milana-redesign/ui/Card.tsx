import type { ReactNode } from "react";

type Props = {
  title: string;
  children: ReactNode;
  meta?: string;
};

export function Card({ title, children, meta }: Props) {
  return (
    <article className="glass-card">
      {meta ? <p className="card-meta">{meta}</p> : null}
      <h3>{title}</h3>
      <div>{children}</div>
    </article>
  );
}
