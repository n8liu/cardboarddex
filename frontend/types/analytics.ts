export interface TrafficCounts { views: number; visitors: number; sessions: number }
export interface StatsReport {
  start: string;
  end: string;
  timezone: string;
  updated_at: string;
  tracking_started_at: string | null;
  tracking_enabled: boolean;
  earliest_report_date: string;
  total_views: number;
  total_visitors: number;
  current: TrafficCounts;
  previous: TrafficCounts | null;
  daily: (TrafficCounts & { day: string })[];
  countries: (TrafficCounts & { country: string })[];
  pages: (TrafficCounts & { path: string })[];
}
