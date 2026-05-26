export type Item = {
  description: string;
  hsn: string;
  qty: string;
  unit: string;
  rate: string;
  amount: string;
};

export type ParsedData = {
  buyer: string;
  subject: string;
  ref: string;
  date: string;
  gst_percent: string;
  gstin?: string;
  signatory: string;
  items: Item[];
  terms: string[];
  _engine?: string;
};

export type Letterhead = {
  id: string;
  company: string;
  original_name: string;
  storage_path: string;
  created_at: string;
};

export type GenResult = {
  n: number;
  company: string;
  letterhead: string;
  summary: string;
  docx_url: string | null;
  pdf_url: string | null;
};

export type GenError = {
  n: number;
  company: string;
  letterhead: string;
  error: string;
};

export const EMPTY_ITEM: Item = {
  description: "",
  hsn: "",
  qty: "",
  unit: "",
  rate: "",
  amount: "",
};
