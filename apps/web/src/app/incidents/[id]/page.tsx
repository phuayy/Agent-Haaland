import { IncidentDetail } from "@/components/incident/incident-detail";

export default async function IncidentPage({
  params,
}: PageProps<"/incidents/[id]">) {
  const { id } = await params;
  return <IncidentDetail id={id} />;
}
