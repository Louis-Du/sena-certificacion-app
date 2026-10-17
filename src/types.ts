export type InformationType = 'df14a' | 'certificados' | 'pendientes' | 'acta' | 'requisitos' | 'otro';

export interface Learner {
  id: number;
  identification: string;
  name: string;
  program: string | null;
  group_code: string | null;
  training_type: string | null;
  certification_status: string | null;
  start_date?: string | null;
  termination_date?: string | null;
  tracking_notes?: string | null;
}

export interface Requirement {
  id?: number | null;
  learner_id: number;
  requirement_type: string;
  label?: string;
  status: 'Pendiente' | 'Cumplido' | 'No aplica';
  observations: string | null;
}

export interface Act {
  id: number;
  number: string;
  act_date: string;
  act_type: string | null;
  original_file: string;
  review_status: 'pending' | 'reviewed' | 'rejected';
  observations: string | null;
}

export interface ActLearner {
  id: number;
  act_id: number;
  learner_id: number;
  observations: string | null;
}

export interface ImportHistoryItem {
  id: number;
  file_name: string;
  information_type: string;
  imported_at: string;
  records_count: number;
  new_records: number;
  updated_records: number;
  warning_count: number;
  error_count: number;
  user_name: string | null;
  status: string;
  message: string | null;
}

export interface ValidationCheck {
  label: string;
  status: 'ok' | 'warning' | 'error' | 'info';
}

export interface ExtractedActLearner {
  identification: string;
  name: string;
  program?: string;
  group_code?: string;
  observations?: string;
  existing_learner_id?: number | null;
}

export interface ExtractedActData {
  number: string;
  act_date: string;
  act_type: string;
  original_file: string;
  observations: string;
  learners: ExtractedActLearner[];
}

export interface ValidationResult {
  validation_id: string;
  file_name: string;
  information_type: InformationType;
  status: 'ready' | 'warning' | 'error';
  checks: ValidationCheck[];
  records_found?: number | null;
  valid_records?: number | null;
  inconsistencies: number;
  message: string;
  detected_columns?: string[];
  missing_columns?: string[];
  extra_columns?: string[];
  records?: Record<string, any>[];
  extracted_act?: ExtractedActData;
}

export interface ImportPreviewData {
  validation_id: string;
  file_name: string;
  information_type: string;
  records_count: number;
  new_records: number;
  updated_records: number;
  warnings: string[];
  status: 'ready' | 'warning' | 'error';
}

export interface IndicatorMetric {
  category: 'superior' | 'tecnica' | 'articulacion' | 'complementaria';
  categoryLabel: string;
  meta: number;
  certificadosPeriodo: number; // Enero - Septiembre 2026
  pendientesPeriodo: number;
  porcentajeAvance: number; // (certificados / meta) * 100
  brecha: number; // meta - certificados
  tasaEfectividad: number; // certificados / (certificados + pendientes) * 100
}

export interface IndicadoresSummary {
  periodo: string; // "Enero - Septiembre 2026"
  totalMeta: number;
  totalCertificados: number;
  totalPendientes: number;
  totalIncidenciasCausas: number;
  aprendicesConCausasMultiples: number;
  porcentajeAvanceGlobal: number;
  tasaEfectividadGlobal: number;
  metricasPorCategoria: IndicatorMetric[];
  pendientesPorMotivo: Array<{ motivo: string; cantidad: number; porcentaje: number }>;
  ultimasActasPeriodo: Array<{ id: number; number: string; fecha: string; aprendicesCount: number; tipo: string }>;
}

export const REQUIREMENT_TYPES: Record<string, string> = {
  learning_outcome: 'Resultados de aprendizaje / RAP',
  documentation: 'Documentación',
  productive_stage: 'Etapa productiva',
  clearance: 'Paz y salvo',
  saber_tyt: 'Saber TyT',
};

export const REQUIREMENT_STATUSES = ['Pendiente', 'Cumplido', 'No aplica'] as const;

export const TYPE_LABELS: Record<InformationType, string> = {
  df14a: 'DF14A',
  certificados: 'Listado de certificados',
  pendientes: 'Listado de pendientes',
  acta: 'Acta de certificacion',
  requisitos: 'Requisitos / pendientes',
  otro: 'Otro archivo',
};

export const EXTENSIONS_BY_TYPE: Record<InformationType, string[]> = {
  df14a: ['.xlsx', '.xls', '.csv', '.xml'],
  certificados: ['.xlsx', '.xls', '.csv'],
  pendientes: ['.xlsx', '.xls', '.csv'],
  acta: ['.docx', '.pdf', '.xlsx', '.xls'],
  requisitos: ['.xlsx', '.xls', '.csv'],
  otro: ['.xlsx', '.xls', '.csv', '.xml', '.pdf', '.docx'],
};

export const REQUIRED_COLUMNS: Record<string, string[]> = {
  df14a: ['FICHA'],
  certificados: ['NUMERO DE DOCUMENTO', 'NOMBRE', 'FICHA'],
  pendientes: ['NUMERO DE DOCUMENTO', 'NOMBRE', 'FICHA'],
  requisitos: ['DOCUMENTO', 'NOMBRES', 'REQUISITO', 'ESTADO'],
  acta: [],
  otro: [],
};
