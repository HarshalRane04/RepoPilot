import { getDashboardData, publicApiBaseUrl } from "../lib/api";
import { OperatorConsole } from "./operator-console";

export default async function Home() {
  const data = await getDashboardData();
  return <OperatorConsole apiBaseUrl={publicApiBaseUrl()} initialData={data} />;
}
