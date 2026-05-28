import { CTASection } from "@/components/CTASection";
import { Hero } from "@/components/Hero";
import { PortfolioGrid } from "@/components/PortfolioGrid";
import { Reviews } from "@/components/Reviews";
import { ServicesGrid } from "@/components/ServicesGrid";
import { socialProof, whyUs } from "@/lib/constants";

export default function HomePage() {
  return (
    <>
      <Hero />
      <section className="social-proof section">
        {socialProof.map((item) => (
          <div key={item} className="proof-pill">{item}</div>
        ))}
      </section>
      <ServicesGrid />
      <PortfolioGrid />
      <section className="section">
        <div className="section-head">
          <p className="kicker">Why Us</p>
          <h2>Почему выбирают нас</h2>
        </div>
        <div className="cards-grid">
          {whyUs.map((item) => (
            <article key={item.title} className="glass-card">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>
      <Reviews />
      <CTASection />
    </>
  );
}
