import { Card } from "@/ui/Card";

const facts = [
  { title: "Команда", text: "Проектировщики и монтажники с отточенными регламентами работ." },
  { title: "Подход", text: "Каждый проект ведется как мини-продукт: бриф, смета, контроль качества." },
  { title: "Ответственность", text: "Договор, прозрачные этапы и постгарантийная поддержка." }
];

export default function AboutPage() {
  return (
    <section className="section page-hero">
      <p className="kicker">About</p>
      <h1>О компании Milana</h1>
      <div className="cards-grid" style={{ marginTop: "1.2rem" }}>
        {facts.map((fact) => (
          <Card key={fact.title} title={fact.title}>
            <p>{fact.text}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
