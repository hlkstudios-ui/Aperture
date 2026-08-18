import { redirect } from "next/navigation";
export default function SeriesIndex() {
  redirect("/studio/content?type=series");
}
