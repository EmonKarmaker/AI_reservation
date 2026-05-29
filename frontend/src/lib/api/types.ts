// Shared API types mirroring the backend Pydantic schemas.

export type UserRole = "super_admin" | "business_admin";

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  business_id: string | null;
}

export interface LoginResponse {
  user: UserOut;
}

export interface MeResponse {
  user: UserOut;
}

export interface BusinessOut {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  industry: string | null;
  timezone: string;
  currency: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  address: string | null;
  logo_url: string | null;
  status: string;
  ai_personality: string | null;
  ai_greeting: string | null;
  booking_window_days: number;
  cancellation_hours: number;
}

export interface ServiceOut {
  id: string;
  business_id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  buffer_minutes: number;
  price: string; // Decimal serialized as string
  is_active: boolean;
  display_order: number;
  image_url: string | null;
}

export interface FaqOut {
  id: string;
  business_id: string;
  question: string;
  answer: string;
  category: string | null;
  is_active: boolean;
  display_order: number;
}

export type DayOfWeek = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export interface OperatingHoursDay {
  day_of_week: DayOfWeek;
  open_time: string | null;
  close_time: string | null;
  is_closed: boolean;
}

export interface OperatingHoursOut {
  days: OperatingHoursDay[];
}

// Error shape thrown by the API client.
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
