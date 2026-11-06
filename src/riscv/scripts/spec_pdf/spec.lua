-- deterministic layout rules for block specs
local function latex(blocks)
  local s = pandoc.write(pandoc.Pandoc(blocks), 'latex')
  s = s:gsub('%s+$', '')
  return (s:gsub('\\_', '\\_\\allowbreak{}'))
end

local function widths(rows, n)
  local w, total = {}, 0
  for c = 1, n do
    local longest = 6
    for _, row in ipairs(rows) do
      local t = pandoc.utils.stringify(row.cells[c].contents)
      if #t > longest then longest = #t end
    end
    w[c] = math.min(longest, 60) ^ 0.75
    total = total + w[c]
  end
  for c = 1, n do w[c] = w[c] / total end
  return w
end

function Table(tbl)
  local rows = {}
  for _, r in ipairs(tbl.head.rows) do rows[#rows + 1] = r end
  local nhead = #rows
  for _, b in ipairs(tbl.bodies) do
    for _, r in ipairs(b.body) do rows[#rows + 1] = r end
  end
  local n = #tbl.colspecs
  local w = widths(rows, n)
  local spec = {}
  for c = 1, n do
    spec[c] = string.format('>{\\raggedright\\arraybackslash}p{\\dimexpr %.4f\\linewidth-2\\tabcolsep-1.2\\arrayrulewidth\\relax}', w[c])
  end
  local out = {'\\begingroup\\footnotesize', '\\begin{longtable}{|' .. table.concat(spec, '|') .. '|}', '\\hline'}
  for i, r in ipairs(rows) do
    local cells = {}
    for c = 1, n do
      local t = latex(r.cells[c].contents)
      if i <= nhead then t = '\\textbf{' .. t .. '}' end
      cells[c] = t
    end
    out[#out + 1] = table.concat(cells, ' & ') .. ' \\\\ \\hline'
    if i == nhead then out[#out + 1] = '\\endhead' end
  end
  out[#out + 1] = '\\end{longtable}\\endgroup'
  return pandoc.RawBlock('latex', table.concat(out, '\n'))
end

function CodeBlock(cb)
  return pandoc.RawBlock('latex', '\\begin{Verbatim}[fontsize=\\scriptsize]\n' .. cb.text .. '\n\\end{Verbatim}')
end

-- links to other specs have no target inside one pdf
function Link(l)
  if l.target:match('%.md') then return l.content end
end
