import { redirect } from "next/navigation";
export default function MoviesIndex() {
  redirect("/studio/content?type=movie");
}
