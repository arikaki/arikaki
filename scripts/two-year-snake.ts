/**
 * Generates a snake animation covering the last two years of a user's GitHub
 * contributions, instead of the single year the stock Platane/snk action uses.
 *
 * GitHub only allows `contributionsCollection` ranges of up to one year, so the
 * graph is fetched as two consecutive windows and stitched into one grid.
 *
 * This file is copied into a checkout of Platane/snk (see
 * .github/workflows/snake.yml) so it can reuse snk's solver and SVG writer.
 *
 * Env:
 *   GITHUB_TOKEN        token for the GraphQL API (required)
 *   SNAKE_USER          GitHub login to read (required)
 *   SNAKE_OUT_DIR       output directory (default: dist)
 *   GITHUB_GRAPHQL_URL  override for testing (default: https://api.github.com/graphql)
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getBestRoute } from "@snk/solver/getBestRoute";
import { getPathToPose } from "@snk/solver/getPathToPose";
import { createSvg } from "@snk/svg-creator";
import { snake4 } from "@snk/types/__fixtures__/snake";
import { cellsToGrid } from "./cellsToGrid";
import { palettes } from "./palettes";

type Level = 0 | 1 | 2 | 3 | 4;
type Day = { date: string; level: Level };

const DAY_MS = 86_400_000;
// GitHub rejects contributionsCollection ranges longer than one year.
const WINDOW_DAYS = 365;

const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
const utc = (date: string) => new Date(`${date}T00:00:00Z`).getTime();

/** Two consecutive one-year windows ending today (oldest first). */
export const getWindows = (today: string) => {
  const end = utc(today);
  const recentFrom = end - (WINDOW_DAYS - 1) * DAY_MS;
  const olderTo = recentFrom - DAY_MS;
  const olderFrom = olderTo - (WINDOW_DAYS - 1) * DAY_MS;
  return [
    { from: iso(olderFrom), to: iso(olderTo) },
    { from: iso(recentFrom), to: iso(end) },
  ];
};

const LEVELS: Record<string, Level> = {
  FOURTH_QUARTILE: 4,
  THIRD_QUARTILE: 3,
  SECOND_QUARTILE: 2,
  FIRST_QUARTILE: 1,
  NONE: 0,
};

const QUERY = /* GraphQL */ `
  query ($login: String!, $from: DateTime!, $to: DateTime!) {
    user(login: $login) {
      contributionsCollection(from: $from, to: $to) {
        contributionCalendar {
          weeks {
            contributionDays {
              contributionLevel
              date
            }
          }
        }
      }
    }
  }
`;

const fetchWindow = async (
  login: string,
  from: string,
  to: string,
  token: string,
  apiUrl: string,
): Promise<Day[]> => {
  const maxAttempts = 4;
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(apiUrl, {
        method: "POST",
        headers: {
          Authorization: `bearer ${token}`,
          "Content-Type": "application/json",
          "User-Agent": "two-year-snake",
        },
        body: JSON.stringify({
          query: QUERY,
          variables: {
            login,
            from: `${from}T00:00:00Z`,
            to: `${to}T23:59:59Z`,
          },
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const body = (await res.json()) as any;
      if (body.errors?.[0]) throw new Error(body.errors[0].message);

      const weeks =
        body.data.user.contributionsCollection.contributionCalendar.weeks;
      return (weeks as any[])
        .flatMap((w) => w.contributionDays as any[])
        .map((d) => ({ date: d.date as string, level: LEVELS[d.contributionLevel] ?? 0 }))
        // The calendar returns whole weeks; keep only days inside the window.
        .filter((d) => d.date >= from && d.date <= to);
    } catch (error) {
      if (attempt === maxAttempts) throw error;
      const delayMs = 2000 * 2 ** (attempt - 1);
      console.warn(
        `attempt ${attempt}/${maxAttempts} failed (${(error as Error).message}); retrying in ${delayMs / 1000}s`,
      );
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
};

/**
 * Stitch several windows into one continuous grid:
 * x = week index (Sunday-based), y = weekday (0 = Sunday).
 */
export const mergeWindows = (windows: Day[][]) => {
  const byDate = new Map<string, Day>();
  for (const w of windows) for (const d of w) byDate.set(d.date, d);
  const days = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  if (days.length === 0) throw new Error("no contribution days returned");

  const first = utc(days[0].date);
  const origin = first - new Date(first).getUTCDay() * DAY_MS; // previous Sunday

  return days.map(({ date, level }) => ({
    x: Math.floor((utc(date) - origin) / DAY_MS / 7),
    y: new Date(utc(date)).getUTCDay(),
    date,
    level,
  }));
};

const main = async () => {
  const token = process.env.GITHUB_TOKEN;
  const user = process.env.SNAKE_USER;
  if (!token || !user) throw new Error("GITHUB_TOKEN and SNAKE_USER are required");
  const outDir = process.env.SNAKE_OUT_DIR ?? "dist";
  const apiUrl = process.env.GITHUB_GRAPHQL_URL ?? "https://api.github.com/graphql";

  const windows = getWindows(iso(Date.now()));
  console.log(`fetching ${user}: ${windows.map((w) => `${w.from}..${w.to}`).join(" + ")}`);

  const fetched: Day[][] = [];
  for (const w of windows) fetched.push(await fetchWindow(user, w.from, w.to, token, apiUrl));

  const cells = mergeWindows(fetched);
  const grid = cellsToGrid(cells);
  console.log(`cells=${cells.length} grid=${grid.width}x${grid.height}`);

  const chain = getBestRoute(grid, snake4)!;
  chain.push(...getPathToPose(chain.slice(-1)[0], snake4)!);

  const base = { sizeDotBorderRadius: 2, sizeCell: 16, sizeDot: 12 };
  const outputs = [
    ["github-snake-2y.svg", { ...base, ...palettes["default"] }],
    ["github-snake-2y-dark.svg", { ...base, ...palettes["github-dark"] }],
  ] as const;

  mkdirSync(outDir, { recursive: true });
  for (const [name, drawOptions] of outputs) {
    const svg = createSvg(grid, cells, chain, drawOptions as any, {
      frameByStep: 1,
      stepDurationMs: 100,
    } as any);
    writeFileSync(join(outDir, name), svg);
    console.log(`wrote ${join(outDir, name)} (${(svg.length / 1024).toFixed(0)} KB)`);
  }
};

if (import.meta.main) await main();
