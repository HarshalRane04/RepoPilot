import { getDashboardData, publicApiBaseUrl } from "../lib/api";
import { OperatorConsole } from "./operator-console";
import { headers } from "next/headers";

export default async function Home() {
  const cookieHeader = (await headers()).get("cookie") ?? undefined;
  const data = await getDashboardData(cookieHeader);
  return <OperatorConsole apiBaseUrl={publicApiBaseUrl()} initialData={data} />;
}
