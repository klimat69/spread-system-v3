"use client";

import { useForm } from "react-hook-form";

import { Button } from "@/ui/Button";

type LeadForm = {
  name: string;
  phone: string;
};

export function CTASection() {
  const { register, handleSubmit, reset, formState } = useForm<LeadForm>();

  const onSubmit = (data: LeadForm) => {
    console.log("lead", data);
    reset();
  };

  return (
    <section className="section cta-final" id="lead-form">
      <div className="section-head">
        <p className="kicker">Final CTA</p>
        <h2>Оставьте заявку за 30 секунд</h2>
      </div>
      <form className="lead-form" onSubmit={handleSubmit(onSubmit)}>
        <label>
          Имя
          <input placeholder="Ваше имя" {...register("name", { required: true, minLength: 2 })} />
        </label>
        <label>
          Телефон
          <input placeholder="+7 (___) ___-__-__" {...register("phone", { required: true, minLength: 10 })} />
        </label>
        <Button type="submit">Получить консультацию</Button>
      </form>
      {formState.isSubmitSuccessful ? <p className="form-success">Заявка отправлена. Менеджер свяжется в течение 15 минут.</p> : null}
    </section>
  );
}
