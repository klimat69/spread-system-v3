import { reviews } from "@/lib/constants";

export function Reviews() {
  return (
    <section className="section">
      <div className="section-head">
        <p className="kicker">Reviews</p>
        <h2>Отзывы клиентов и рейтинг</h2>
      </div>
      <div className="cards-grid">
        {reviews.map((review) => (
          <article key={review.name} className="glass-card review-card">
            <div className="review-top">
              <div className="avatar" aria-hidden>{review.name[0]}</div>
              <div>
                <h3>{review.name}</h3>
                <p>{"★".repeat(review.rating)}</p>
              </div>
            </div>
            <p>{review.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
