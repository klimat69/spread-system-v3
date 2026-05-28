"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";

import { portfolio } from "@/lib/constants";

export function PortfolioGrid() {
  const [beforeAfter, setBeforeAfter] = useState(52);

  return (
    <section className="section">
      <div className="section-head">
        <p className="kicker">Portfolio</p>
        <h2>Портфолио с фокусом на результат</h2>
      </div>
      <div className="masonry-grid">
        <article className="glass-card before-after">
          <h3>Before / After</h3>
          <p>Слайдер сравнения показывает разницу до и после работ.</p>
          <div className="before-after-visual">
            <div className="before" />
            <div className="after" style={{ width: `${beforeAfter}%` }} />
          </div>
          <label>
            Сравнение
            <input type="range" min={10} max={95} value={beforeAfter} onChange={(e) => setBeforeAfter(Number(e.target.value))} />
          </label>
        </article>
        {portfolio.map((item) => (
          <motion.article key={item.title} className="glass-card" whileHover={{ scale: 1.02 }}>
            <p className="card-meta">{item.type}</p>
            <h3>{item.title}</h3>
            <p>{item.result}</p>
            <Link href="/contacts">Запросить похожий проект</Link>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
