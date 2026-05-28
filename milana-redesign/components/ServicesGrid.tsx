"use client";

import { motion } from "framer-motion";
import Link from "next/link";

import { hoverLift, staggerContainer, fadeUp } from "@/lib/animations";
import { services } from "@/lib/constants";

export function ServicesGrid() {
  return (
    <section className="section">
      <div className="section-head">
        <p className="kicker">Services</p>
        <h2>Услуги, которые сразу ведут к заявке</h2>
      </div>
      <motion.div className="cards-grid" variants={staggerContainer} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.15 }}>
        {services.map((item) => (
          <motion.article key={item.title} className="glass-card" variants={fadeUp} initial="rest" whileHover="hover" animate="rest" transition={{ duration: 0.24 }}>
            <motion.div variants={hoverLift}>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <Link href="/contacts">{item.cta}</Link>
            </motion.div>
          </motion.article>
        ))}
      </motion.div>
    </section>
  );
}
