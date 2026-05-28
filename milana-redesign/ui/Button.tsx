"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "secondary";
  type?: "button" | "submit";
  onClick?: () => void;
};

export function Button({ children, href, variant = "primary", type = "button", onClick }: Props) {
  const className = variant === "primary" ? "btn btn-primary" : "btn btn-secondary";

  if (href) {
    return (
      <motion.div whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
        <Link href={href} className={className}>
          {children}
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.button type={type} onClick={onClick} className={className} whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
        {children}
    </motion.button>
  );
}
