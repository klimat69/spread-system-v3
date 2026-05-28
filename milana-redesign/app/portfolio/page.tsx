import { CTASection } from "@/components/CTASection";
import { PortfolioGrid } from "@/components/PortfolioGrid";

export default function PortfolioPage() {
  return (
    <>
      <section className="section page-hero">
        <p className="kicker">Portfolio</p>
        <h1>Реальные работы, реальные бюджеты</h1>
      </section>
      <PortfolioGrid />
      <CTASection />
    </>
  );
}
