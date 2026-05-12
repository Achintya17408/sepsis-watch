import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Modal } from './Modal';
import { bulkAdmitPatients } from '../api';

const OPTIONAL_NUM = ['age'];
const WARDS = ['MICU', 'SICU', 'CCU', 'CSRU', 'General'];

interface ParsedRow {
  [key: string]: string | number | undefined;
}

function parseCSV(text: string): ParsedRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/\s+/g, '_').replace(/"/g, ''));
  return lines.slice(1).map((line) => {
    const values = line.split(',').map((v) => v.trim().replace(/"/g, ''));
    const row: ParsedRow = {};
    headers.forEach((h, i) => {
      const v = values[i] ?? '';
      if (OPTIONAL_NUM.includes(h) && v !== '') row[h] = parseInt(v, 10);
      else if (v !== '') row[h] = v;
    });
    return row;
  }).filter((r) => r.name); // skip fully empty rows
}

const SAMPLE_CSV = `name,age,ward,hospital_id
Alice Kumar,62,MICU,MRN-001
Bob Patel,45,SICU,MRN-002
Carol Singh,71,CCU,MRN-003`;

export function BulkUploadModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<ParsedRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [parseError, setParseError] = useState('');
  const [result, setResult] = useState<{ admitted: number; errors: { row: number; name: unknown; error: string }[] } | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setParseError('');
    setResult(null);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      try {
        const parsed = parseCSV(text);
        if (parsed.length === 0) {
          setParseError('No valid rows found. Check the CSV has a header row and at least one data row.');
          setRows([]);
        } else {
          setRows(parsed);
        }
      } catch {
        setParseError('Failed to parse CSV.');
        setRows([]);
      }
    };
    reader.readAsText(file);
  };

  const upload = async () => {
    setUploading(true);
    const res = await bulkAdmitPatients(rows as Record<string, unknown>[]);
    setResult(res);
    setUploading(false);
    if (res.admitted > 0) qc.invalidateQueries({ queryKey: ['patients'] });
  };

  const downloadSample = () => {
    const blob = new Blob([SAMPLE_CSV], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'sample_patients.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Modal title="Bulk Admit Patients (CSV)" onClose={onClose}>
      <div className="space-y-4">
        {/* Instructions */}
        <div className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600 space-y-1">
          <p className="font-medium">CSV column reference</p>
          <p><span className="font-semibold text-slate-800">Required:</span> name</p>
          <p><span className="font-semibold text-slate-800">Optional:</span> age, ward ({WARDS.join(' / ')}), hospital_id</p>
          <button onClick={downloadSample} className="text-blue-600 underline underline-offset-2">
            Download sample CSV
          </button>
        </div>

        {/* File picker */}
        <div>
          <label className="label">Select CSV file</label>
          <div
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 py-6 hover:border-blue-400"
            onClick={() => fileRef.current?.click()}
          >
            <span className="text-2xl">📂</span>
            <span className="text-sm text-slate-500">
              {fileName ? fileName : 'Click to choose a .csv file'}
            </span>
          </div>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={handleFile} />
        </div>

        {parseError && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{parseError}</p>
        )}

        {/* Preview */}
        {rows.length > 0 && !result && (
          <div>
            <p className="label">{rows.length} row{rows.length !== 1 ? 's' : ''} ready · preview (first 5)</p>
            <div className="overflow-x-auto rounded-xl border border-slate-100">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    {Object.keys(rows[0]).map((k) => (
                      <th key={k} className="px-3 py-1.5 text-left">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.slice(0, 5).map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-3 py-1.5 text-slate-700">{String(v ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              className="btn-primary mt-3 w-full"
              disabled={uploading}
              onClick={upload}
            >
              {uploading ? `Admitting ${rows.length} patients…` : `Admit ${rows.length} Patients`}
            </button>
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-2">
            <div className={`rounded-xl px-4 py-3 text-sm ${result.admitted > 0 ? 'bg-green-50 text-green-800' : 'bg-slate-50 text-slate-600'}`}>
              ✅ {result.admitted} patient{result.admitted !== 1 ? 's' : ''} admitted successfully
            </div>
            {result.errors.length > 0 && (
              <div className="rounded-xl bg-red-50 px-4 py-3 text-xs text-red-700 space-y-1">
                <p className="font-semibold">⚠️ {result.errors.length} row{result.errors.length !== 1 ? 's' : ''} failed:</p>
                {result.errors.map((err) => (
                  <p key={err.row}>Row {err.row} ({String(err.name)}): {err.error}</p>
                ))}
              </div>
            )}
            <button className="btn-ghost w-full" onClick={onClose}>Done</button>
          </div>
        )}
      </div>
    </Modal>
  );
}
