import React, { useState, useEffect } from 'react';
import { IndicadoresSummary } from '../types';
import { getIndicadores2026 } from '../storage';

export const IndicadoresView: React.FC = () => {
  const [data, setData] = useState<IndicadoresSummary | null>(null);

  useEffect(() => {
    setData(getIndicadores2026());
  }, []);

  if (!data) {
    return (
      <div className="panel">
        <p>Calculando indicadores consolidados...</p>
      </div>
    );
  }

  return (
    <div id="indicadores-view" className="app-view">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          %
        </div>
        <div>
          <p className="eyebrow">Sena Certificación</p>
          <h1>Indicadores de Certificación 2026</h1>
          <p className="subtitle">
            Seguimiento de metas, ejecución y pendientes para el período{' '}
            <strong>{data.periodo}</strong>.
          </p>
        </div>
        <span className="prototype-note">◈ Centro de Comercio y Servicios · Regional Bolívar</span>
      </header>

      {/* Global KPI Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
          marginBottom: '18px',
        }}
      >
        <div className="panel" style={{ padding: '14px' }}>
          <small style={{ color: 'var(--muted)', fontWeight: 700, fontSize: '10px' }}>
            META ANUAL VIGENTE
          </small>
          <h2 style={{ fontSize: '24px', margin: '4px 0 2px', color: 'var(--ink)' }}>
            {data.totalMeta.toLocaleString('es-CO')}
          </h2>
          <small style={{ color: 'var(--muted)', fontSize: '11px' }}>Aprendices proyectados</small>
        </div>

        <div className="panel" style={{ padding: '14px', borderLeft: '4px solid var(--green)' }}>
          <small style={{ color: 'var(--green-dark)', fontWeight: 700, fontSize: '10px' }}>
            EJECUTADOS (ENE-SEP)
          </small>
          <h2 style={{ fontSize: '24px', margin: '4px 0 2px', color: 'var(--green-dark)' }}>
            {data.totalCertificados.toLocaleString('es-CO')}
          </h2>
          <small style={{ color: 'var(--muted)', fontSize: '11px' }}>Aprendices certificados únicos</small>
        </div>

        <div className="panel" style={{ padding: '14px', borderLeft: '4px solid #b87d00' }}>
          <small style={{ color: '#b87d00', fontWeight: 700, fontSize: '10px' }}>
            PENDIENTES POR CUMPLIR
          </small>
          <h2 style={{ fontSize: '24px', margin: '4px 0 2px', color: '#b87d00' }}>
            {data.totalPendientes.toLocaleString('es-CO')}
          </h2>
          <small style={{ color: 'var(--muted)', fontSize: '11px' }}>En proceso de certificación</small>
        </div>

        <div className="panel" style={{ padding: '14px', background: 'var(--green-soft)' }}>
          <small style={{ color: 'var(--green-dark)', fontWeight: 700, fontSize: '10px' }}>
            % AVANCE DE META
          </small>
          <h2 style={{ fontSize: '24px', margin: '4px 0 2px', color: 'var(--green-dark)' }}>
            {data.porcentajeAvanceGlobal}%
          </h2>
          <small style={{ color: 'var(--green-dark)', fontSize: '11px' }}>Ejecución acumulada</small>
        </div>

        <div className="panel" style={{ padding: '14px' }}>
          <small style={{ color: 'var(--muted)', fontWeight: 700, fontSize: '10px' }}>
            EFECTIVIDAD DE CIERRE
          </small>
          <h2 style={{ fontSize: '24px', margin: '4px 0 2px', color: 'var(--ink)' }}>
            {data.tasaEfectividadGlobal}%
          </h2>
          <small style={{ color: 'var(--muted)', fontSize: '11px' }}>Certificados vs candidatos</small>
        </div>
      </div>

      {/* Main Grid: Categories & Pending Breakdown */}
      <div className="workspace-grid" style={{ gridTemplateColumns: 'minmax(0, 1.8fr) minmax(310px, 1fr)' }}>
        <section className="main-column">
          {/* Detailed Categories Table */}
          <article className="panel">
            <div className="panel-heading">
              <div>
                <h2>Ejecución por Nivel y Tipo de Formación</h2>
                <p>Consolidado sin duplicidad de aprendices entre actas (Ene - Sep 2026)</p>
              </div>
            </div>

            <div className="learners-table-wrap">
              <table className="learners-data">
                <thead>
                  <tr>
                    <th>Categoría Operativa</th>
                    <th>Meta</th>
                    <th>Certificados</th>
                    <th>Pendientes</th>
                    <th>% Avance</th>
                    <th>Brecha</th>
                    <th>Efectividad</th>
                  </tr>
                </thead>
                <tbody>
                  {data.metricasPorCategoria.map((cat) => (
                    <tr key={cat.category}>
                      <td>
                        <strong>{cat.categoryLabel}</strong>
                      </td>
                      <td>{cat.meta.toLocaleString('es-CO')}</td>
                      <td style={{ color: 'var(--green-dark)', fontWeight: 700 }}>
                        {cat.certificadosPeriodo.toLocaleString('es-CO')}
                      </td>
                      <td style={{ color: '#b87d00' }}>{cat.pendientesPeriodo.toLocaleString('es-CO')}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <div
                            style={{
                              width: '60px',
                              height: '8px',
                              background: '#e2ede7',
                              borderRadius: '4px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${Math.min(cat.porcentajeAvance, 100)}%`,
                                height: '100%',
                                background: 'var(--green)',
                              }}
                            />
                          </div>
                          <span>{cat.porcentajeAvance}%</span>
                        </div>
                      </td>
                      <td>{cat.brecha > 0 ? cat.brecha.toLocaleString('es-CO') : 'Cumplida'}</td>
                      <td>
                        <span className="result-badge ready">{cat.tasaEfectividad}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          {/* Actas in the period */}
          <article className="panel">
            <div className="panel-heading">
              <div>
                <h2>Actas Registradas en el Período 2026</h2>
                <p>Documentos que sustentan la certificación de aprendices (Enero - Septiembre)</p>
              </div>
            </div>
            <div className="learners-table-wrap">
              <table className="learners-data">
                <thead>
                  <tr>
                    <th>Número de Acta</th>
                    <th>Fecha</th>
                    <th>Tipo</th>
                    <th>Aprendices Certificados</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ultimasActasPeriodo.map((act) => (
                    <tr key={act.id}>
                      <td>
                        <strong>{act.number}</strong>
                      </td>
                      <td>{act.fecha}</td>
                      <td>{act.tipo}</td>
                      <td>{act.aprendicesCount}</td>
                      <td>
                        <span className="result-badge ready">Revisada</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        {/* Side Column: Reasons of Pending & Rules */}
        <aside className="side-column">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <h2>Distribución de Pendientes</h2>
                <p>Principales causas de no certificación</p>
              </div>
            </div>
            <div style={{ display: 'grid', gap: '10px' }}>
              {data.pendientesPorMotivo.map((mot) => (
                <div
                  key={mot.motivo}
                  style={{
                    background: '#f8faf9',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid var(--line)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <strong style={{ fontSize: '11px' }}>{mot.motivo}</strong>
                    <span style={{ fontSize: '11px', color: '#b87d00', fontWeight: 700 }}>
                      {mot.cantidad} ({mot.porcentaje}%)
                    </span>
                  </div>
                  <div
                    style={{
                      width: '100%',
                      height: '6px',
                      background: '#eee',
                      borderRadius: '3px',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${mot.porcentaje}%`,
                        height: '100%',
                        background: '#d48b00',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <p style={{ marginTop: '12px', fontSize: '11px', color: 'var(--muted)', lineHeight: '1.4' }}>
              ◈ <strong>Auditoría de consistencia:</strong> Se registran <strong>{data.totalPendientes}</strong> aprendices únicos pendientes y <strong>{data.totalIncidenciasCausas}</strong> incidencias totales de causas. La diferencia de <strong>{data.totalIncidenciasCausas - data.totalPendientes}</strong> caso(s) corresponde a causas múltiples por aprendiz (concurrencia de requisitos simultáneos no superados).
            </p>
          </article>

          <article className="panel guidance-panel">
            <h2>Reglas Metodológicas Confirmadas</h2>
            <p>Directrices técnicas de cálculo</p>
            <ul>
              <li>
                <strong>Criterio de unicidad:</strong> Cada aprendiz se contabiliza una única vez por identificación
                en el período, evitando duplicados si aparece en múltiples actas.
              </li>
              <li>
                <strong>Período evaluado:</strong> 1 de enero de 2026 al 30 de septiembre de 2026.
              </li>
              <li>
                <strong>Fórmula de Avance:</strong> (Ejecución acumulada / Meta) * 100%.
              </li>
              <li>
                <strong>Fórmula de Brecha:</strong> Meta menos aprendices certificados (mínimo 0).
              </li>
              <li>
                <strong>Educación Superior:</strong> Corresponde exclusivamente a nivel Tecnólogo.
              </li>
              <li>
                <strong>Técnica Laboral:</strong> Incluye Técnicos, Auxiliares, Operarios y programas Senatic.
              </li>
            </ul>
          </article>
        </aside>
      </div>
    </div>
  );
};
