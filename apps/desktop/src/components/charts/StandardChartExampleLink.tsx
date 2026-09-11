import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { standardChartDemo } from "@/data/standardChartDemo";
import { useLocale } from "@/locales/LocaleProvider";

/** Entering a demonstration is explicit; a deep link never changes account scope. */
export function StandardChartExampleLink() {
  const data = useDataMode();
  const { locale } = useLocale();
  const episode = standardChartDemo.entry.episode;
  const example = data.examples.find((item) => item.subjectId === episode.subjectId && item.accountId === episode.accountId);
  if (!example) return null;
  return <Link className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-accent hover:bg-white/5 focus-visible:outline focus-visible:outline-2" to={`/investments/episodes/${episode.episodeId}`} onClick={() => {
    data.setExampleAccount(example);
    data.setMode("demo");
  }}>{locale === "zh-CN" ? "打开标准 K 线示例" : "Open the candlestick example"}<ArrowUpRight className="size-4" aria-hidden="true" /></Link>;
}
