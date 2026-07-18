import { SchoolMap } from "./SchoolMap";

// MVP: the landing map section now renders the De School–style grid component
// instead of the dotted-map WorldMap. WorldMap.tsx and the `dotted-map` dep are
// left in place, so reverting is a one-line change back to the old section.
export function Placeholder() {
  return <SchoolMap />;
}
