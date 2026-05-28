import Link from "next/link";

export function Footer() {
  return (
    <footer className="footer">
      <p>© {new Date().getFullYear()} Milana. Conversion-first redesign.</p>
      <Link href="/contacts">Контакты</Link>
    </footer>
  );
}
