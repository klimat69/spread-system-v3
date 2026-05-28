import { ServicesGrid } from "@/components/ServicesGrid";
import { CTASection } from "@/components/CTASection";

export default function ServicesPage() {
  return (
    <>
      <section className="section page-hero">
        <p className="kicker">Services</p>
        <h1>Услуги под задачи вашего дома</h1>
      </section>
      <ServicesGrid />
      <CTASection />
    </>
  );
}
