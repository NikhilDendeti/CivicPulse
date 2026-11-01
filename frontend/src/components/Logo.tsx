export default function Logo({ size = 32, text = true }: { size?: number; text?: boolean }) {
  return (
    <span className="logo">
      <img src="/icon.svg" width={size} height={size} alt="" />
      {text && <span className="logo-text">Civic<b>Pulse</b></span>}
    </span>
  );
}
