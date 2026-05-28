export const fadeUp = {
  hidden: { opacity: 0, y: 26 },
  show: { opacity: 1, y: 0 }
};

export const staggerContainer = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.12
    }
  }
};

export const hoverLift = {
  rest: { y: 0, scale: 1 },
  hover: { y: -8, scale: 1.01 }
};
