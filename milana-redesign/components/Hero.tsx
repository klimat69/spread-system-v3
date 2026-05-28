"use client";

import { motion } from "framer-motion";

import { fadeUp } from "@/lib/animations";
import { Button } from "@/ui/Button";

export function Hero() {
  return (
    <section className="hero">
      <div className="hero-bg" aria-hidden>
        <div className="gradient-orb orb-a" />
        <div className="gradient-orb orb-b" />
      </div>
      <motion.div initial="hidden" animate="show" variants={fadeUp} transition={{ duration: 0.6 }} className="hero-content">
        <p className="kicker">Modern Conversion UI</p>
        <h1>Премиальные решения для вашего дома</h1>
        <p className="subtitle">Проектирование • монтаж • гарантия</p>
        <div className="cta-row">
          <Button href="/contacts">Получить расчёт</Button>
          <Button href="/portfolio" variant="secondary">Посмотреть работы</Button>
        </div>
      </motion.div>
    </section>
  );
}
