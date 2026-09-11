import orb from "@/assets/glass-orb.png";
import "./glass-orb-logo.css";

/** Local, independent artwork. The circular viewport excludes the source backdrop. */
export function GlassOrbLogo({ prominent = false }: { prominent?: boolean }) {
  return <span className={`glass-orb-logo ${prominent ? "glass-orb-logo--prominent" : ""}`} aria-hidden="true"><img src={orb} alt="" draggable={false} /></span>;
}
