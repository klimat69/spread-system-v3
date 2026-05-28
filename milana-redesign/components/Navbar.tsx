import Link from "next/link";

import { Button } from "@/ui/Button";

export function Navbar() {
  return (
    <header className="navbar">
      <Link href="/" className="brand">MILANA</Link>
      <nav>
        <Link href="/services">Услуги</Link>
        <Link href="/portfolio">Портфолио</Link>
        <Link href="/about">О нас</Link>
        <Link href="/contacts">Контакты</Link>
      </nav>
      <Button href="/contacts">Получить расчёт</Button>
    </header>
  );
}
