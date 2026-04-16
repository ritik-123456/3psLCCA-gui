
import os
import json
import argparse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pylatex import (
    Document,
    Section,
    Subsection,
    Subsubsection,
    Tabular,
    Package,
    NoEscape,
    Figure,
    NewPage,
    Center,
)
from pylatex.utils import bold, escape_latex
from pylatex import NoEscape

from three_ps_lcca_gui.report.lcca_template import (
    LCCATemplate,
    KEY_SHOW_BRIDGE_DESC,
    KEY_SHOW_FINANCIAL,
    KEY_SHOW_CONSTRUCTION,
    KEY_SHOW_LCC_ASSUMPTIONS,
    KEY_SHOW_USE_STAGE,
    KEY_SHOW_AVG_TRAFFIC,
    KEY_SHOW_ROAD_TRAFFIC,
    KEY_SHOW_PEAK_HOUR,
    KEY_SHOW_HUMAN_INJURY,
    KEY_SHOW_VEHICLE_DAMAGE,
    KEY_SHOW_TYRE_COST,
    KEY_SHOW_FUEL_OIL,
    KEY_SHOW_NEW_VEHICLE,
    KEY_SHOW_SOCIAL_CARBON,
    KEY_SHOW_MATERIAL_EMISSION,
    KEY_SHOW_USE_EMISSION,
    KEY_SHOW_VEHICLE_EMISSION,
    KEY_SHOW_ONSITE_EMISSION,
    KEY_FRAMEWORK_FIGURE,
    KEY_BRIDGE_DESC,
    KEY_FINANCIAL,
    KEY_CONSTRUCTION,
    KEY_LCC_ASSUMPTIONS,
    KEY_USE_STAGE,
    KEY_AVG_TRAFFIC,
    KEY_ROAD_TRAFFIC,
    KEY_PEAK_HOUR,
    KEY_HUMAN_INJURY,
    KEY_VEHICLE_DAMAGE,
    KEY_TYRE_COST,
    KEY_FUEL_OIL,
    KEY_NEW_VEHICLE,
    KEY_SOCIAL_CARBON,
    KEY_MATERIAL_EMISSION,
    KEY_USE_EMISSION,
    KEY_VEHICLE_EMISSION,
    KEY_ONSITE_EMISSION,
    KEY_TRANSPORT_EMISSION,
    KEY_SHOW_TRANSPORT_EMISSION,
    KEY_LCC_TABLE1,
    KEY_STAGE_COSTS,
    KEY_PILLAR_COSTS,
    KEY_ECONOMIC_COSTS,
    KEY_SOCIAL_COSTS,
    KEY_RUC_CONSTRUCTION,
    KEY_ENVIRONMENTAL_COSTS_37,
)



class LCCAReportLatex(Document):


    def __init__(self):
        """Initialize Document with geometry, packages, and preamble."""
        geometry = {
            "tmargin": "1in",
            "bmargin": "1in",
            "lmargin": "1in",
            "rmargin": "1in",
        }
        super().__init__(geometry_options=geometry, document_options=["12pt", "a4paper"])

        # Packages
        self.packages.append(Package("graphicx"))
        self.packages.append(Package("float"))
        self.packages.append(Package("caption"))
        self.packages.append(Package("needspace"))
        self.packages.append(Package("longtable"))
        self.packages.append(Package("array"))
        self.packages.append(Package("chngcntr"))
        self.packages.append(Package("amsmath"))
        self.packages.append(Package("xcolor", options=["table"]))
        self.packages.append(Package("colortbl"))
        self.packages.append(Package("newtxtext"))
        self.packages.append(Package("newtxmath"))
        self.packages.append(Package("multirow"))
        self.packages.append(
            Package(
                "hyperref",
                options=["colorlinks=true", "linkcolor=black", "urlcolor=blue"],
            )
        )

        # Preamble - match the clean docx look
        self.preamble.append(NoEscape(r"""
\renewcommand{\arraystretch}{1.2}
\setlength{\tabcolsep}{5pt}
\pagestyle{plain}
\counterwithin{table}{section}
\counterwithin{figure}{section}
\renewcommand{\thetable}{\thesection-\arabic{table}}
\renewcommand{\thefigure}{\thesection-\arabic{figure}}
"""))


    def add_lcca_results(self, config, data):
        """Section 3: LCCA Results - Tables 3-1 through 3-7."""
        with self.create(Section("LCCA results")):
            self.append(
                "This chapter presents software-generated numerical results "
                "in tabular and graphical formats."
            )

            # ── 3.1 Life cycle cost results ──────────────────────────────────
            with self.create(Subsection("Life cycle cost results")):
                self.append(NoEscape(
                    r"The total life cycle cost of the bridge is "
                    r"\underline{\hspace{4cm}}. "
                    r"The contribution of different life cycle cost components "
                    r"is provided in the \textit{Table 3-1} below."
                ))
                self.append(NoEscape(r"\vspace{4pt}"))
                self.append(NoEscape(r"\needspace{8\baselineskip}"))
                self.append(NoEscape(
                    r"\noindent\captionof{table}{Contribution of different "
                    r"life cycle cost components}"
                ))
                self.append(NoEscape(r"\vspace{4pt}"))
                # ── longtable: auto page-break, header repeats on each page ──
                lcc = data.get(KEY_LCC_TABLE1, {})
                col_spec = (
                    r"|>{\raggedright\arraybackslash}p{1.6cm}"
                    r"|>{\raggedright\arraybackslash}p{4.5cm}"
                    r"|>{\raggedright\arraybackslash}p{2.3cm}"
                    r"|>{\raggedright\arraybackslash}p{1.0cm}"
                    r"|>{\raggedright\arraybackslash}p{1.2cm}"
                    r"|>{\raggedright\arraybackslash}p{1.2cm}"
                    r"|>{\raggedright\arraybackslash}p{1.1cm}"
                    r"|>{\raggedright\arraybackslash}p{1.1cm}|"
                )
                # Build header row LaTeX string
                header_row = (
                    r" & \textbf{Costs} & \textbf{Cost in Present time}"
                    r" & \textbf{in cr} & \textbf{in lakhs} & \textbf{in Millions}"
                    r" & \textbf{\% of initial cost} & \textbf{\% LCC} \\"
                )
                # Build all data rows as raw LaTeX
        
                rows_tex = ""
                for stage_label, stage_rows in lcc.items():
                    first = True
                    row_count = len(stage_rows)
                    cost_items = list(stage_rows.items())

                    for idx, (cost_label, vals) in enumerate(cost_items):
                        from pylatex.utils import escape_latex as el

                        if first:
                            # \parbox inside \multirow forces text to wrap within the column width
                            stage_cell = (
    r"\multirow{" + str(row_count) + r"}{*}"
    r"{\parbox[t]{1.5cm}{\raggedright\footnotesize\textbf{\hspace{0pt}" + el(stage_label) + r"}}}"
)
                            first = False
                        else:
                            stage_cell = ""

                        cells = [stage_cell, r"\textbf{" + el(cost_label) + r"}"]
                        cells += [el(str(v)) for v in vals]
                        rows_tex += " & ".join(cells) + r" \\" + "\n"

                        # Between rows in the same group: \cline skipping col 1 (preserves multirow visual)
                        # After the last row in a group: full \hline
                        if idx < row_count - 1:
                            rows_tex += r"\cline{2-8}" + "\n"
                        else:
                            rows_tex += r"\hline" + "\n"

                longtable_tex = (
                    r"{\footnotesize" + "\n"
                    r"\begin{longtable}{" + col_spec + r"}" + "\n"
                    r"\hline" + "\n"
                    + header_row + "\n"
                    r"\hline" + "\n"
                    # First-page head ends here
                    r"\endfirsthead" + "\n"
                    # Continuation header (repeated on every new page)
                    r"\hline" + "\n"
                    + header_row + "\n"
                    r"\hline" + "\n"
                    r"\endhead" + "\n"
                    # Footer on all pages except last
                    r"\endfoot" + "\n"
                    # Last-page footer - nothing
                    r"\hline" + "\n"
                    r"\endlastfoot" + "\n"
                    # Data rows
                    + rows_tex
                    + r"\end{longtable}" + "\n"
                    r"}"
                )
                self.append(NoEscape(longtable_tex))
                self.append(NoEscape(r"\vspace{4pt}"))

            # ── 3.2 Stage-wise distribution ──────────────────────────────────
            with self.create(Subsection("Stage-wise distribution of life cycle costs")):
                self.add_kv_table(
                    "Life cycle stage wise costs",
                    data.get(KEY_STAGE_COSTS, {}),
                    col1="7.5cm", col2="7cm",
                )

            # ── 3.3 Pillar-wise distribution ─────────────────────────────────
            with self.create(Subsection("Pillar-wise distribution of life cycle costs")):
                self.add_kv_table(
                    "Sustainability pillar wise cost",
                    data.get(KEY_PILLAR_COSTS, {}),
                    col1="7.5cm", col2="7cm",
                )

                # ── 3.3.1 Economic costs ──────────────────────────────────────
                with self.create(Subsubsection("Economic costs")):
                    self.append(
                        "Different components of economic pillar of sustainability"
                    )
                    self.add_kv_table(
                        "Economic cost results across different stages",
                        data.get(KEY_ECONOMIC_COSTS, {}),
                        col1="9cm", col2="5.5cm",
                    )

                # ── 3.3.2 Social costs ────────────────────────────────────────
                with self.create(Subsubsection("Social costs")):
                    self.append(
                        "Road user cost during different life cycle stages"
                    )
                    self.add_kv_table(
                        "Social cost across different stages",
                        data.get(KEY_SOCIAL_COSTS, {}),
                        col1="9cm", col2="5.5cm",
                    )
                    self.add_kv_table(
                        "Road user costs during construction",
                        data.get(KEY_RUC_CONSTRUCTION, {}),
                        col1="7.5cm", col2="7cm",
                    )

                # ── 3.3.3 Environmental costs ─────────────────────────────────
                with self.create(Subsubsection("Environmental costs")):
                    self.append(
                        "Environmental cost contribution across the bridge life cycle."
                    )
                    self.add_kv_table(
                        "Environmental costs across different stages",
                        data.get(KEY_ENVIRONMENTAL_COSTS_37, {}),
                        col1="10cm", col2="4.5cm",
                    )


    def add_full_appendix(self):
        appendix_tex = r"""

\clearpage

\section*{\fontsize{14pt}{16pt}\selectfont\bfseries Summary and Conclusions}

\noindent
The LCCA results indicate the relative contribution of construction, road user, and environmental costs, supporting informed and sustainable bridge planning decisions.

\vspace{0.3em}

\noindent
The most contributing stage of the life cycle is \underline{\hspace{3cm}} 
contributing to around \underline{\hspace{2cm}}\% of the total life cycle cost.

\vspace{0.3em}

\noindent
The most contributing pillar is \underline{\hspace{3cm}} contributing to around \underline{\hspace{2cm}}\% of the total life cycle cost.

\vspace{0.5em}

\begin{itemize}
\item User conclusions or remarks.
\end{itemize}

\vspace{0.5em}

\textbf{Note:} The above life cycle cost calculations do not include all components of
the 3PS-LCC framework. Certain cost elements have been excluded from the analysis.
The specific life cycle cost components that were included and excluded in the above
calculations are listed below.

\vspace{0.5em}

\textbf{Life cycle cost components (Included)}

\begin{itemize}
\item Initial construction costs
\item Initial carbon emissions (materials)
\item Initial carbon emissions (on-site)
\item Initial carbon emission (transportation of material)
\item Time costs
\item Road user costs during initial construction
\item Carbon emissions due to rerouting during initial construction (vehicles)
\item Routine inspection costs
\item Periodic maintenance costs
\item Periodic maintenance carbon emissions (materials)
\item Major inspection costs
\item Major repair costs
\item Major repair-related carbon emissions (materials)
\item Road user costs during major repairs
\item Carbon emissions due to rerouting during major repairs (vehicles)
\item Replacement cost of bearings and expansion joints
\item Road user costs during replacement
\item Carbon emissions due to rerouting during replacement (vehicles)
\item Demolition and disposal costs of the existing bridge
\item Demolition and disposal-related carbon emissions (materials) of the existing bridge
\item Road user costs during demolition and disposal of the existing bridge
\item Carbon emissions due to rerouting during demolition and disposal (vehicles) of the existing bridge
\item Recycling costs for reconstruction
\item Reconstruction costs
\item Reconstruction carbon emissions (materials)
\item Reconstruction time costs
\item Road user costs during reconstruction
\item Carbon emissions due to rerouting during reconstruction (vehicles)
\item Final demolition and disposal costs
\item Final demolition and disposal-related carbon emissions (materials)
\item Road user costs during final demolition and disposal
\item Carbon emissions due to rerouting during final demolition and disposal (vehicles)
\item Recycling costs
\end{itemize}
....\\
....\\
....\\

\vspace{0.5em}

\textbf{Life cycle cost components (Excluded)}\\
\vspace{0.5em}
....


\clearpage
\appendix
\pagestyle{empty}

\section*{\fontsize{14pt}{16pt}\selectfont\bfseries Appendix A: Assumptions}

\noindent
This Life Cycle Cost Assessment (LCCA) has been carried out using a deterministic,
software-based approach. The analysis is based on standard engineering practice,
published guidelines, and reasonable assumptions adopted to ensure consistency,
transparency, and comparability of results. The key assumptions adopted in the
present study are summarized below.

\vspace{0.5em}

\begin{itemize}
\item The analysis period corresponds to the \textbf{design/service life of the bridge} as specified in the project data.
\item The study includes: initial construction, routine inspection, periodic maintenance, major inspections, repairs, replacement of bearings and expansion joints, reconstruction, demolition and disposal, and associated road user costs.
\item Only greenhouse gas (GHG) emissions are considered for environmental cost monetization.
\item Other impacts such as noise pollution, local business impacts, regional economic disruptions, and broader social externalities are outside the scope of this study.
\item Components not explicitly defined in the input data or methodology are excluded.
\item Future technological advancement, policy changes, traffic growth variations, or economic structural shifts are not considered.
\item All costs are converted into present value terms.
\item The discounting approach is based on standard economic theory where future costs and benefits are adjusted to present value using a constant discount rate.
\item Inflation and interest rates are assumed constant over the analysis period.
\item Real interest rate principles are used in deriving the discount relationship.
\item Wholesale Price Index (WPI) ratios are used for escalation of specific cost components based on their respective commodity categories. WPI categories are used for adjusting the following components:
  \begin{itemize}
  \item Passenger and crew cost $\rightarrow$ ``All Commodities''
  \item Property damage and spare parts $\rightarrow$ ``Manufacture of parts and accessories for motor vehicles''
  \item Human injury cost $\rightarrow$ ``Medical accessories''
  \item Petrol $\rightarrow$ ``Mineral Oils''
  \item Diesel $\rightarrow$ ``HSD (High Speed Diesel)''
  \item Engine oil $\rightarrow$ ``Lube oils''
  \item Grease and related oils $\rightarrow$ ``Mineral oil (grouped)''
  \item Tyre costs (by vehicle category) $\rightarrow$ Corresponding tyre index categories
  \item Fixed and depreciation cost $\rightarrow$ ``Manufacture of motor vehicles, trailers and semi-trailers''
  \item Commodity holding cost $\rightarrow$ ``Fuel \& Power''
  \end{itemize}
\item Initial construction costs are based on estimated quantities and prevailing unit rates from SOR.
\item Carbon emissions during construction are calculated using emission factors for material, transportation and energy consumption.
\item Emission factors are assumed constant over the entire analysis period.
\item Transportation of materials occurs under normal traffic and operating conditions.
\item Maintenance and repair emissions are assumed proportional to initial construction emissions.
\item Demolition and disposal emissions are assumed proportional to construction emissions.
\item Recycling is assumed to generate cost recovery (treated as negative cost).
\item Environmental cost is calculated by monetizing carbon emissions using a single Social Cost of Carbon (SCC) value.
\item Average Daily Traffic (ADT) is assumed constant within each defined analysis period.
\item Traffic composition (cars, two-wheelers, buses, LCVs, HCVs, MCVs) is based on input data.
\item Traffic diversion during construction, maintenance, repair, replacement, reconstruction, and demolition is assumed over a predefined detour length.
\item Vehicle operating cost, value of time, and accident cost are calculated using standard equations and accepted parameters.
\item Uniform traffic flow and average operating conditions are assumed during rerouting.
\item Routine inspections, periodic maintenance, major inspections, and repairs occur at fixed predefined intervals.
\item Maintenance and repair costs are calculated as a percentage of initial construction or superstructure cost.
\item Replacement activities are limited to bearings and expansion joints.
\item Reconstruction involves demolition of the existing bridge followed by construction of a new bridge with similar functional characteristics.
\item All interventions occur as scheduled without unplanned delays unless explicitly stated.
\end{itemize}


\clearpage

\appendix
\pagestyle{empty}

\section*{\fontsize{14pt}{16pt}\selectfont\bfseries Appendix A: Assumptions}

\noindent
This Life Cycle Cost Assessment (LCCA) has been carried out using a deterministic,
software-based approach grounded in standard engineering practice, published literature,
and national economic data. The assumptions adopted ensure consistency, transparency,
and comparability of results.

\vspace{0.5em}

\begin{itemize}
\item The analysis period corresponds to the \textbf{design/service life of the bridge} as specified in the project data.
\item The study includes: initial construction, routine inspection, periodic maintenance, major inspections, repairs, replacement of bearings and expansion joints, reconstruction, demolition and disposal, and associated road user costs.
\item Only greenhouse gas (GHG) emissions are considered for environmental cost monetization.
\item Other impacts such as noise pollution, local business impacts, regional economic disruptions, and broader social externalities are outside the scope of this study.
\item Components not explicitly defined in the input data or methodology are excluded.
\item Future technological advancement, policy changes, traffic growth variations, or economic structural shifts are not considered.
\item All costs are converted into present value terms.
\item The discounting approach is based on standard economic theory where future costs and benefits are adjusted to present value using a constant discount rate.
\item Inflation and interest rates are assumed constant over the analysis period.
\item Real interest rate principles are used in deriving the discount relationship.
\item Wholesale Price Index (WPI) ratios are used for escalation of specific cost components based on their respective commodity categories. WPI categories are used for adjusting the following components:
  \begin{itemize}
  \item Passenger and crew cost $\rightarrow$ ``All Commodities''
  \item Property damage and spare parts $\rightarrow$ ``Manufacture of parts and accessories for motor vehicles''
  \item Human injury cost $\rightarrow$ ``Medical accessories''
  \item Petrol $\rightarrow$ ``Mineral Oils''
  \item Diesel $\rightarrow$ ``HSD (High Speed Diesel)''
  \item Engine oil $\rightarrow$ ``Lube oils''
  \item Grease and related oils $\rightarrow$ ``Mineral oil (grouped)''
  \item Tyre costs (by vehicle category) $\rightarrow$ Corresponding tyre index categories
  \item Fixed and depreciation cost $\rightarrow$ ``Manufacture of motor vehicles, trailers and semi-trailers''
  \item Commodity holding cost $\rightarrow$ ``Fuel \& Power''
  \end{itemize}
\item Initial construction costs are based on estimated quantities and prevailing unit rates from SOR.
\item Carbon emissions during construction are calculated using emission factors for material, transportation and energy consumption.
\item Emission factors are assumed constant over the entire analysis period.
\item Transportation of materials occurs under normal traffic and operating conditions.
\item Maintenance and repair emissions are assumed proportional to initial construction emissions.
\item Demolition and disposal emissions are assumed proportional to construction emissions.
\item Recycling is assumed to generate cost recovery (treated as negative cost).
\item Environmental cost is calculated by monetizing carbon emissions using a single Social Cost of Carbon (SCC) value.
\item Average Daily Traffic (ADT) is assumed constant within each defined analysis period.
\item Traffic composition (cars, two-wheelers, buses, LCVs, HCVs, MCVs) is based on input data.
\item Traffic diversion during construction, maintenance, repair, replacement, reconstruction, and demolition is assumed over a predefined detour length.
\item Vehicle operating cost, value of time, and accident cost are calculated using standard equations and accepted parameters.
\item Uniform traffic flow and average operating conditions are assumed during rerouting.
\item Routine inspections, periodic maintenance, major inspections, and repairs occur at fixed predefined intervals.
\item Maintenance and repair costs are calculated as a percentage of initial construction or superstructure cost.
\item Replacement activities are limited to bearings and expansion joints.
\item Reconstruction involves demolition of the existing bridge followed by construction of a new bridge with similar functional characteristics.
\item All interventions occur as scheduled without unplanned delays unless explicitly stated.
\end{itemize}
\newpage
\section*{\fontsize{14pt}{16pt}\selectfont\bfseries Appendix B: Calculation Methodology}

\noindent
This chapter presents the calculation method and equations used for cost calculations.
The glossary for the terms used in the equations are mentioned below.

\vspace{0.5em}

\begin{itemize}
\item $A_{Di}$ = Accident distribution
\item $A_{Ne}$ = Number of accidents for each vehicle type
\item $A_{Tn}$ = Total number of accidents in the stipulated time
\item $C_{Di}$ = Distance related cost
\item $CF_D$ = Distance related congestion factor
\item $CF_T$ = Time related congestion factor
\item $C_{Ti}$ = Time related cost
\item $DC_m$ = Duration of construction in months
\item $D_{ma}$ = Number of equipment usage days
\item $D_{wm}$ = Number of working days in a month
\item $Di$ = Distance travelled for transportation of material
\item $EF_m$ = Emission factor for materials
\item $EF_{ma}$ = Emission factor for energy consumption
\item $EF_{tp}$ = Emission factor for transportation
\item $EF_v$ = Vehicular emission factor
\item $E_{VD}$ = Vehicle damage cost
\item $E_{Vi}$ = Economic cost of injury
\item $Q_{rm}$ = Quantity of recycle material
\item $RE_c$ = Recycling cost
\item $T_{AT}$ = Additional travel time
\item $T_{VP}$ = Time value
\item $V/C$ = Volume-Capacity ratio
\item $V_{CD}$ = Vehicle counts per day
\item $\mathrm{AC}$ = Accident cost
\item $\mathrm{CC}$ = Cargo capacity
\item $\mathrm{CFU}$ = Price of fuel
\item $\mathrm{CHC}$ = Commodity holding cost
\item $\mathrm{COF}$ = Conversion factor
\item $\mathrm{CR}$ = Crash rate
\item $\mathrm{CW}$ = Crew cost
\item $\mathrm{DC}$ = Depreciation cost
\item $\mathrm{D_{cf}}$ = Demolition and disposal cost
\item $\mathrm{D_{cr}}$ = Demolition and disposal cost for reconstruction
\item $\mathrm{DC_{y}}$ = Duration of construction (years)
\item $\mathrm{DF_{EC}}$ = Emission cost for end-of-life demolition
\item $\mathrm{DR_{EC}}$ = Emission cost for demolition during reconstruction
\item $\mathrm{EOL}$ = Engine oil consumption
\item $\mathrm{EOLC}$ = Engine oil cost
\item $\mathrm{EOL_{P}}$ = Engine oil price
\item $\mathrm{F_{C}}$ = Fuel cost
\item $\mathrm{FC_{CB}}$ = Fuel consumption petrol
\item $\mathrm{FC_{CS}}$ = Fuel consumption diesel
\item $\mathrm{FL}$ = Fall
\item $\mathrm{FXC}$ = Fixed cost
\item $\mathrm{G}$ = Grease consumption
\item $\mathrm{GC}$ = Grease cost
\item $\mathrm{G_{P}}$ = Grease price
\item $I$ = Interest rate
\item $\mathrm{IC}$ = Initial construction cost
\item $\mathrm{IR}$ = Investment ratio
\item $\mathrm{LC}$ = Maintenance labour cost
\item $\mathrm{MIc}$ = Major inspection cost
\item $\mathrm{MR_{c}}$ = Major repair cost
\item $\mathrm{MR_{EC}}$ = Major repair emission cost
\item $n$ = Design life (years)
\item $\mathrm{NP}$ = New vehicle cost
\item $\mathrm{O_{Avg}}$ = Average occupancy of a vehicle
\item $\mathrm{OL}$ = Other oil consumption
\item $\mathrm{OLC}$ = Other oil cost
\item $\mathrm{OL_{P}}$ = Other oil price
\item $\mathrm{P_{IC}}$ = Percentage of initial construction cost
\item $\mathrm{P_{IEC}}$ = Percentage of initial carbon emission
\item $\mathrm{PMc}$ = Periodic maintenance cost
\item $\mathrm{PM_{EC}}$ = Periodic maintenance emission cost
\item $\mathrm{PT}$ = Passenger time cost
\item $\mathrm{PWF}$ = Present Worth Factor
\item $\mathrm{PWR}$ = Power weight ratio
\item $Q$ = Quantity of material
\item $r$ = Discount rate
\item $R$ = Rate of material
\item $\mathrm{RC_{BE}}$ = Replacement cost of bearing and expansion joint
\item $\mathrm{RCN}$ = Reconstruction cost
\item $\mathrm{RD}$ = Rerouting distance
\item $\mathrm{REC_{EC}}$ = Reconstruction emission cost
\item $\mathrm{RG}$ = Roughness
\item $\mathrm{RI_{c}}$ = Routine inspection cost 
\item $\mathrm{R}$ = Rate of recycle material
\item $\mathrm{RS}$ = Rise
\item $\mathrm{RUC}$ = Road user cost
\item $\mathrm{SP}$ = Spare part cost
\item $\mathrm{TC}$ = Time cost
\item $\mathrm{TYC}$ = Tyre cost
\item $\mathrm{TCe}$ = Cost of each tyre
\item $\mathrm{TCR}$ = Time cost for reconstruction
\item $\mathrm{TL}$ = Tyre life
\item $\mathrm{TN}$ = Number of tyres
\item $\mathrm{UPD}$ = Utilization per day
\item $\mathrm{VOC}$ = Vehicle operating cost
\item $\mathrm{VOT}$ = Value of time cost
\item $\mathrm{W}$ = Width of carriageway
\item $\mathrm{WPI}$ = Wholesale price index
\item $\mathrm{WZM}$ = Work zone multiplier
\item $x$ = Periodic interval (years)
\item $\mathrm{ADT}$ = Average daily traffic
\item $\mathrm{IEC}$ = Initial emission cost
\item $\mathrm{IAEC}$ = Initial carbon emission cost from on-site activities
\item $\mathrm{IETC}$ = Initial carbon emission cost due to transportation of material
\item $\mathrm{SCC}$ = Social cost of carbon
\item $\mathrm{VEC}$ = Vehicular emission cost
\item $\mathrm{IAEC}$ = Initial on-site emission cost
\item $\mathrm{ECR}$ = Energy consumption rate
\item $H$ = Average machinery hours per day
\item $D_{ma}$ = Number of equipment usage days
\item $EF_{ma}$ = Emission factor for machinery energy use
\end{itemize}

\vspace{0.5em}

{\fontsize{13pt}{15pt}\selectfont\bfseries B.1 Initial Cost}

\vspace{0.3em}
\textbf{B.1.1 Economic cost}

\noindent
Initial construction cost
\[
IC = \sum_{i=1}^{n} Q_i \times R_i
\]

\noindent
Time cost
\[
TC = IC \times I \times DC_y \times IR
\]

\vspace{0.3em}
\textbf{B.1.2 Social cost}

\noindent
Road user cost during construction
\[
RUC_{cn} = VOC_{cn} + VOT_{cn} + AC_{cn}
\]
\[
\resizebox{\linewidth}{!}{$\displaystyle
VOC_{cn} = D_{wm} \times DC_m \times RD \times
\left[
  \sum_{j=1}^{o} \left\{ (C_{Ti})_{j} \times (V_{CD})_{j} \times (CF_{T})_{j} \times (WPI_{Ti})_{j} \right\}
  + \sum_{k=1}^{p} \left\{ (C_{Di})_{k} \times (V_{CD})_{k} \times (CF_{D})_{k} \times (WPI_{Di})_{k} \right\}
\right]
$}
\]

\noindent
Distance related costs
\[
F_{Cp} = CFU_{Pe} \times FC_{CS}
\]
\[
F_{Cd} = CFU_{Di} \times FC_{CB}
\]
\[
F_{C} = CFU \times FC
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-1 Fuel Consumption equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\everymath{\fontsize{9pt}{11pt}\selectfont}
\everydisplay{\fontsize{9pt}{11pt}\selectfont}
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{2.80}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small and Big Car &
\makebox[\linewidth][c]{$
\begin{aligned}
FC_{CS} &= 30 + \frac{844.085}{V} + 0.003V^2 + (0.001 \times RG) + (0.3414 \times RS) - (0.2225 \times FL) \\
FC_{CB} &= 35 + \frac{983.503}{V} + 0.003V^2 + (0.002 \times RG) + (0.339 \times RS) - (0.4785 \times FL)
\end{aligned}
$} \\ \hline
Two-wheeler &
\makebox[\linewidth][c]{$FC = 2.704 + \frac{439.656}{V} + 0.00349V^2 + (0.000157 \times RG) + (0.3642 \times RS) - (0.2709 \times FL)$} \\ \hline
Buses &
\makebox[\linewidth][c]{$FC = 34.23 + \frac{4054.42}{V} + 0.02149V^2 + (0.001246 \times RG) + (3.4557 \times RS) - (1.8454 \times FL)$} \\ \hline
LCV &
\makebox[\linewidth][c]{$FC_{CB} = 22.504 + \frac{1708.244}{V} + 0.02591V^2 + (0.001612 \times RG) + (5.6863 \times RS) - (0.8744 \times FL)$} \\ \hline
HCV &
\makebox[\linewidth][c]{$FC_{CB} = 50.0 + \frac{8049.955}{V} + 0.012V^2 + (0.005 \times RG) + (4.565 \times RS) - (4.904 \times FL) - (7.285 \times PWR)$} \\ \hline
MCV &
\makebox[\linewidth][c]{$FC_{CB} = 90.0 + \frac{14489.919}{V} + 0.0216V^2 + (0.01 \times RG) + (8.217 \times RS) - (8.8272 \times FL) - (13.113 \times PWR)$} \\ \hline
\end{tabular}
}
\end{table}

\begin{table}[H]
\centering
\caption*{\textit{Table B-2 Speed equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small Car & \makebox[13.5cm][c]{$V = 81.19 - (0.7892 \times RF) - [0.001891 \times (RG - 2000)]$} \\ \hline
Big Car & \makebox[13.5cm][c]{$V = 81.92 - (0.7963 \times RF) - [0.001915 \times (RG - 2000)]$} \\ \hline
Two-wheeler & \makebox[13.5cm][c]{$V = 59.71 - (0.7892 \times RF) - [0.001891 \times (RG - 2000)]$} \\ \hline
Buses & \makebox[13.5cm][c]{$V = 54.23 - (0.4111 \times RF) - [0.00098 \times (RG - 2000)]$} \\ \hline
LCV & \makebox[13.5cm][c]{$V = 57.41 - (0.5119 \times RF) - [0.00102 \times (RG - 2000)]$} \\ \hline
HCV & \makebox[13.5cm][c]{$V = 96.52 - (0.5040 \times RF) - [0.00100 \times (RG - 2000)]$} \\ \hline
MCV & \makebox[13.5cm][c]{$V = 44.79 - (0.3994 \times RF) - [0.00079 \times (RG - 2000)]$} \\ \hline
\end{tabular}
}
\end{table}
\begin{center}
\textcolor{red}{\textit{(Note: This table of equation is only for two lane road)}}
\end{center}

\[
SP = \frac{SP}{NP} \times NP
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-3 Spare part to New vehicle cost ratio for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small Car & \makebox[13.5cm][c]{$\frac{SP}{NP} = 0.0075 \times (RG - 2000) \times 10^{-5}$} \\ \hline
Big Car & \makebox[13.5cm][c]{$\frac{SP}{NP} = 0.0045 \times (RG - 2000) \times 10^{-5}$} \\ \hline
Two-wheeler & \makebox[13.5cm][c]{$\frac{SP}{NP} = [-55.879 + (0.024 \times RG)] \times 10^{-5}$} \\ \hline
Buses & \makebox[13.5cm][c]{$\frac{SP}{NP} = e^{-9.7871 + (0.007373 \times RF) + (0.0000723 \times RG) + \frac{1.925}{W}}$} \\ \hline
LCV & \makebox[13.5cm][c]{$\frac{SP}{NP} = e^{-10.5615 + (0.000141 \times RG) + \frac{3.493}{W}}$} \\ \hline
HCV and MCV & \makebox[13.5cm][c]{$\frac{SP}{NP} = e^{-9.492638 + (0.0001413 \times RG) + \frac{3.493}{W}}$} \\ \hline
\end{tabular}
}
\end{table}

\[
LC = a \times SP
\]
\textit{a for small car and big car = 1.79934, Two-wheeler = 0.5498, Buses = 1.1781, LCV = 0.85773, HCV and MCV = 0.7912}

\[
TC = \frac{TC_e \times TN}{TL}
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-4 Tyre Life equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small and big car & \makebox[13.5cm][c]{$TL = 68771 - (147.9 \times RF) - (26.72 \times RG/W)$} \\ \hline
Two-wheeler & \makebox[13.5cm][c]{$TL = 47340 - (101.8 \times RF) - (18.39 \times RG/W)$} \\ \hline
Buses & \makebox[13.5cm][c]{$TL = 38519 - (389.52 \times RF) - (1.32 \times RG) + (983.829 \times W)$} \\ \hline
LCV & \makebox[13.5cm][c]{$TL = 22382 - (375.3 \times RF) - (1.037 \times RG) + (3817 \times W)$} \\ \hline
HCV & \makebox[13.5cm][c]{$TL = 24662 - (413.6 \times RF) - (1.142 \times RG) + (4205 \times W)$} \\ \hline
MCV & \makebox[13.5cm][c]{$TL = 23726 - (398 \times RF) - (1.0099 \times RG) + (4046 \times W)$} \\ \hline
\end{tabular}
}
\end{table}

\[
EOLC = EOL \times EOL_{P} \times 10^{-3}
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-5 Engine oil consumption for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small and big car & \makebox[13.5cm][c]{$EOL = 1.8807 + (0.036615 \times RF) + (0.000578 \times RG/W)$} \\ \hline
Two-wheeler & \makebox[13.5cm][c]{$EOL = 0.405 + (0.007899 \times RF) + (0.000125 \times RG/W)$} \\ \hline
Buses & \makebox[13.5cm][c]{$EOL = 0.4303 + (0.001494 \times RF) + (0.0007885 \times RG/W)$} \\ \hline
LCV & \makebox[13.5cm][c]{$EOL = 0.80679 + (0.019496 \times RF) + (0.0001297 \times RG/W)$} \\ \hline
HCV & \makebox[13.5cm][c]{$EOL = 1.0277 + (0.02495 \times RF) + (0.0001782 \times RG/W)$} \\ \hline
MCV & \makebox[13.5cm][c]{$EOL = 1.3826 + (0.03348 \times RF) + (0.002319 \times RG/W)$} \\ \hline
\end{tabular}
}
\end{table}

\[
OLC = OL \times OLP \times 10^{-4}
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-6 Other oil consumption equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small and big car and two-wheeler & \makebox[13.5cm][c]{$OL = 1.631 + (0.05167 \times RF) + (0.001867 \times RG/W)$} \\ \hline
Buses & \makebox[13.5cm][c]{$OL = 3.3201 + (0.002889 \times RF) + (0.0008217 \times RG) - (0.3295 \times W)$} \\ \hline
LCV & \makebox[13.5cm][c]{$OL = 2.0415 + (0.0001058 \times RG)$} \\ \hline
HCV and MCV & \makebox[13.5cm][c]{$OL = 5.1037 + (0.0002646 \times RG)$} \\ \hline
\end{tabular}
}
\end{table}

\[
GC = G \times G_{P} \times 10^{4}
\]

\begin{table}[H]
\centering
\caption*{\textit{Table B-7 Grease consumption equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small car, big car and two-wheeler & \makebox[13.5cm][c]{$G = 2.816 + (0.2007 \times RF)$} \\ \hline
Buses & \makebox[13.5cm][c]{$G = 4.992 + (0.03376 \times RF) + (0.3634 \times W)$} \\ \hline
LCV & \makebox[13.5cm][c]{$G = 0.3661 + (0.0283 \times RF) + (0.000251 \times RG)$} \\ \hline
HCV and MCV & \makebox[13.5cm][c]{$G = 0.9153 + (0.0707 \times RF) + (0.000627 \times RG)$} \\ \hline
\end{tabular}
}
\end{table}

\textbf{Time related costs}

\[
FXC = \frac{b}{UPD}
\]
\textit{b for small car and big car = 395.65, Two-wheeler = 24.32, Buses = 772.89, LCV = 723.80, HCV = 924.28, MCV = 1238.26}

\begin{table}[H]
\centering
\caption*{\textit{Table B-8 Utilization per day equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Small car & \makebox[13.5cm][c]{$UPD = 6.7127 \times V$} \\ \hline
Big Car & \makebox[13.5cm][c]{$UPD = 6.7378 \times V$} \\ \hline
Two-wheeler & \makebox[13.5cm][c]{$UPD = 2.119 \times V$} \\ \hline
Buses & \makebox[13.5cm][c]{$UPD = 22.7134 + (12.2569 \times V)$} \\ \hline
LCV & \makebox[13.5cm][c]{$UPD = 28.807 + (2.1836 \times V)$} \\ \hline
HCV & \makebox[13.5cm][c]{$UPD = 55.6719 + (4.22 \times V)$} \\ \hline
MCV & \makebox[13.5cm][c]{$UPD = 77.7233 + (5.8915 \times V)$} \\ \hline
\end{tabular}
}
\end{table}

\[
DC = \frac{c}{UPD}
\]
\textit{c for small and big cars = 42.83, Two-wheeler = 4.26, Buses = 221, LCV = 120.9, HCV = 154.54 and MCV = 238.54}

For Car and Two wheelers,
\[
PT = \frac{d}{V}
\]

For Buses,
\[
PT = \frac{d}{UPD}
\]
\textit{d for small and big car = 328.06, Two-wheeler = 70.29, Buses = 15509.8}

\textcolor{red}{\textit{(Note: This equation is only for two lane road)}}

\[
CW = \frac{e}{UPD}
\]
\textit{e for Buses = 3775.3, LCV = 900, HCV = 1500 and MCV = 1800}

\[
CHC = \frac{f}{UPD}
\]
\textit{f for LCV = 71.35, HCV = 218.75, MCV = 409.28}

\textcolor{red}{\textit{(Note: This equation is only for two lane road)}}

\textbf{Time related congestion factors}

\begin{table}[H]
\centering
\caption*{\textit{Table B-9 Time related congestion factor equations for different vehicles}}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Cars & \makebox[13.5cm][c]{$CF_T = 1.087 + (0.483 \times V/C)$} \\ \hline
Two-wheelers & \makebox[13.5cm][c]{$CF_T = 0.804 + (0.865 \times V/C)$} \\ \hline
Buses & \makebox[13.5cm][c]{$CF_T = 0.864 + (0.543 \times V/C)$} \\ \hline
LCV & \makebox[13.5cm][c]{$CF_T = 0.925 + (0.573 \times V/C)$} \\ \hline
HCV and MCV & \makebox[13.5cm][c]{$CF_T = 0.878 + (0.561 \times V/C)$} \\ \hline
\end{tabular}
}
\end{table}
\begin{center}
 \textcolor{red}{\textit{(Note: This equation is only for two lane road)}}   
\end{center}


\textbf{Distance related congestion factor}

\begin{table}[H]
\centering
\caption*{\textit{Table B-10 Distance related congestion factor equations for different vehicles }}
{\fontsize{9pt}{11pt}\selectfont
\setlength{\tabcolsep}{6pt}
\renewcommand{\arraystretch}{1.9}
\begin{tabular}{|p{3cm}|p{13.5cm}|}
\hline
Cars & \makebox[13.5cm][c]{$CF_D = 0.893 + (0.259 \times V/C)$} \\ \hline
Two-wheelers & \makebox[13.5cm][c]{$CF_D = 0.917 + (0.112 \times V/C)$} \\ \hline
Buses & \makebox[13.5cm][c]{$CF_D = 0.800 + (1.1 \times V/C)$} \\ \hline
LCV & \makebox[13.5cm][c]{$CF_D = 0.9 + (1.0 \times V/C)$} \\ \hline
HCV & \makebox[13.5cm][c]{$CF_D = 0.925 + (0.482 \times V/C)$} \\ \hline
MCV & \makebox[13.5cm][c]{$CF_D = 0.900 + (1.4 \times V/C)$} \\ \hline
\end{tabular}
}
\end{table}
\begin{center}
    \textcolor{red}{\textit{(Note: This equation is only for two lane road)}}
\end{center}


\[
\resizebox{\linewidth}{!}{$\displaystyle
VOT_{cn} = D_{wm} \times DC_m \times T_{AT} \times
\left[
  \sum_{j=1}^{o} \left\{ (T_{VP})_{j} \times (V_{CD})_{j} \times (O_{Avg})_{j} \times (WPI_{Ti})_{j} \right\}
  + \sum_{k=1}^{p} \left\{ (CHC_{T})_{k} \times (V_{CD})_{k} \times (WPI_{Di})_{k} \right\}
\right]
$}
\]

\[
\resizebox{\linewidth}{!}{$\displaystyle
AC_{cn} = A_{Tn} \times
\left[
  \sum_{j=1}^{o} \left\{ (E_{Vi})_{j} \times (A_{Di})_{j} \times (WPI_{me})_{j} \right\}
  + \sum_{k=1}^{p} \left\{ (E_{VD})_{k} \times (A_{Ne})_{k} \times (WPI_{sp})_{k} \right\}
\right]
$}
\]

\[
A_{Tn} = D_{wm} \times DC_m \times CR \times WZM \times RD \times 10^{-6}
\]

\vspace{0.5em}

\section*{\fontsize{14pt}{16pt}\selectfont\bfseries B.1.3 Environmental cost}

\begin{itemize}
\item Embodied carbon emission cost during construction
\[
IEC = SCC \times \sum_{j=1}^{o} \left[ Q_{j} \times (COF)_{j} \times (EF_{m})_{j} \right]
\]

\item Vehicular emission cost during construction due to rerouting
\[
VEC = SCC \times D_{wm} \times DC_m \times RD \times \sum_{k=1}^{p} \left[ ADT_{k} \times (EF_{v})_{k} \right]
\]

\item Carbon emissions from on-site activities during construction
\[
IAEC = SCC \times \sum_{j=1}^{o} \left[ (ECR)_{j} \times (H)_{j} \times (D_{ma})_{j} \times (EF_{ma})_{j} \right]
\]

\item Carbon emission cost due to transportation of construction material
\[
IETC = SCC \times \sum_{j=1}^{o} \left[ Q_{j} \times Di_{j} \times (EF_{tp})_{j} \right]
\]
\end{itemize}

%----------------------------------------------
{\fontsize{13pt}{15pt}\selectfont\bfseries B.2 Use Stage Cost}

\vspace{0.3em}
\textbf{B.2.1 Economic cost}

\begin{itemize}
  \item \textbf{Routine Inspection cost}
    \[ RI_c = \mathrm{PWF} \times P_{Ics} \]
    \[
\mathrm{PWF} = \sum_{i=1}^{\mathrm{int}\left(\frac{n}{x}\right)-1} \frac{(1+f)^{i x}}{(1+r)^{i x}}
\]
  \item \textbf{Periodic maintenance cost}
    \[ PM_c = \mathrm{PWF} \times P_{ICm} \]
  \item \textbf{Major repair cost}
    \[ MR_c = \mathrm{PWF} \times P_{ICr} \]
  \item \textbf{Major inspection cost}
    \[ MI_c = \mathrm{PWF} \times P_{ICi} \]
  \item \textbf{Replacement cost of bearings and expansion joints}
    \[ RC_{BE} = \mathrm{PWF} \times P_{SCr} \]
\end{itemize}




\vspace{0.3em}
\textbf{B.2.2 Social cost}

\begin{itemize}
  \item \textbf{Road user cost due to rerouting during major repairs}
    \[ RUC_{mr} = VOC_{mr} + VOT_{mr} + AC_{mr} \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOC_{mr} = \mathrm{PWF} \times D_{wm} \times DC_m \times RD \left[
      \sum_{j=1}^{o} \left\{ (C_{Ti})_j \times (V_{CD})_j \times (CF_T)_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (C_{Di})_k \times (V_{CD})_k \times (CF_D)_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    (Refer to table B-1 to B-16 to calculate distance and time related costs for VOC)
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOT_{mr} = \mathrm{PWF} \times D_{wm} \times DC_m \times T_{AT} \left[
      \sum_{j=1}^{o} \left\{ (T_{VP})_j \times (V_{CD})_j \times (O_{Avg})_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (CHC_T)_k \times (V_{CD})_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    AC_{mr} = \mathrm{PWF} \times A_{Tn} \left[
      \sum_{j=1}^{o} \left\{ (E_{Vi})_j \times (A_{Di})_j \times (WPI_{me})_j \right\}
      + \sum_{k=1}^{p} \left\{ (E_{VD})_k \times (A_{Ne})_k \times (WPI_{sp})_k \right\}
    \right]
    $}
    \]

  \item \textbf{Road user cost due to rerouting during major repairs}
    \[ RUC_{rbe} = VOC_{rbe} + VOT_{rbe} + AC_{rbe} \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOC_{rbe} = \mathrm{PWF} \times D_{wm} \times DC_m \times RD \left[
      \sum_{j=1}^{o} \left\{ (C_{Ti})_j \times (V_{CD})_j \times (CF_T)_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (C_{Di})_k \times (V_{CD})_k \times (CF_D)_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    (Refer to table B-1 to B-16 to calculate distance and time related costs for VOC)
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOT_{rbe} = \mathrm{PWF} \times D_{wm} \times DC_m \times T_{AT} \left[
      \sum_{j=1}^{o} \left\{ (T_{VP})_j \times (V_{CD})_j \times (O_{Avg})_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (CHC_T)_k \times (V_{CD})_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    AC_{rbe} = \mathrm{PWF} \times A_{Tn} \left[
      \sum_{j=1}^{o} \left\{ (E_{Vi})_j \times (A_{Di})_j \times (WPI_{me})_j \right\}
      + \sum_{k=1}^{p} \left\{ (E_{VD})_k \times (A_{Ne})_k \times (WPI_{sp})_k \right\}
    \right]
    $}
    \]
\end{itemize}

\vspace{0.3em}
\textbf{B.2.3 Environmental cost}

\begin{itemize}
  \item Carbon emission cost due to periodic maintenance
    \[ PM_{EC} = \mathrm{PWF} \times P_{IECp} \]
  \item Carbon emission cost due to major repairs
    \[ MR_{EC} = \mathrm{PWF} \times P_{IECm} \]
  \item Carbon emission due to rerouting of vehicles during major repairs
    \[
    VEC_{MR} = \mathrm{PWF} \times \mathrm{SCC} \times D_{wm} \times DC_m \times RD
    \times \sum_{k=1}^{p} \left[(ADT)_k \times (EF_v)_k\right]
    \]
  \item Carbon emission cost due to replacement of bearings and expansion joints
    \[ RC_{BEE} = \mathrm{PWF} \times P_{IESr} \]
  \item Carbon emission due to rerouting of vehicles during replacement of bearings and expansion joints
    \[
    VEC_{RE} = \mathrm{PWF} \times \mathrm{SCC} \times D_{wm} \times DC_m \times RD
    \times \sum_{k=1}^{p} \left[(ADT)_k \times (EF_v)_k\right]
    \]
\end{itemize}

%----------------------------------------------
{\fontsize{13pt}{15pt}\selectfont\bfseries B.3 End-of-Life Stage Cost Calculation}

\vspace{0.3em}
\textbf{B.3.1 Economic cost}

\begin{itemize}
  \item \textbf{Demolition and disposal cost for reconstruction}
    \[ D_{cr} = \mathrm{PWF} \times P_{ICd} \]
  \item \textbf{Reconstruction cost}
    \[ \mathrm{RCN} = \mathrm{PWF} \times \mathrm{IC} \]
  \item \textbf{Time cost for reconstruction of bridge}
    \[ \mathrm{TCR} = \bigl| \mathrm{PWF} \times \mathrm{TC} \bigr| \]
  \item \textbf{Demolition cost at end of life}
    \[ D_{cf} = \mathrm{PWF} \times P_{ICd} \]
  \item \textbf{Recycling cost}
    \[ RE_c = \mathrm{PWF} \times \sum_{i=0}^{m} (RS)_i \times (Q_{rm})_i \]
\end{itemize}

\vspace{0.3em}
\textbf{B.3.2 Social cost}

\begin{itemize}
  \item \textbf{Road user cost due to rerouting of vehicles during demolition for reconstruction}
    \[ \mathrm{RUC}_{dr} = \mathrm{VOC}_{dr} + \mathrm{VOT}_{dr} + \mathrm{AC}_{dr} \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOC_{dr} = \mathrm{PWF} \times D_{wm} \times DC_m \times RD \left[
      \sum_{j=1}^{o} \left\{ (C_{Ti})_j \times (V_{CD})_j \times (CF_T)_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (C_{Di})_k \times (V_{CD})_k \times (CF_D)_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOT_{dr} = \mathrm{PWF} \times D_{wm} \times DC_m \times T_{AT} \left[
      \sum_{j=1}^{o} \left\{ (T_{VP})_j \times (V_{CD})_j \times (O_{Avg})_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (CHC_T)_k \times (V_{CD})_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    AC_{dr} = \mathrm{PWF} \times A_{Tn} \left[
      \sum_{j=1}^{o} \left\{ (E_{Vi})_j \times (A_{Di})_j \times (WPI_{me})_j \right\}
      + \sum_{k=1}^{p} \left\{ (E_{VD})_k \times (A_{Ne})_k \times (WPI_{sp})_k \right\}
    \right]
    $}
    \]

  \item \textbf{Road user cost due to rerouting of vehicles during reconstruction}
    \[ \mathrm{RUC}_{re} = \mathrm{VOC}_{re} + \mathrm{VOT}_{re} + \mathrm{AC}_{re} \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOC_{re} = \mathrm{PWF} \times D_{wm} \times DC_m \times RD \left[
      \sum_{j=1}^{o} \left\{ (C_{Ti})_j \times (V_{CD})_j \times (CF_T)_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (C_{Di})_k \times (V_{CD})_k \times (CF_D)_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    (Refer to table B-1 to B-16 to calculate distance and time related costs for VOC)
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOT_{re} = \mathrm{PWF} \times D_{wm} \times DC_m \times T_{AT} \left[
      \sum_{j=1}^{o} \left\{ (T_{VP})_j \times (V_{CD})_j \times (O_{Avg})_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (CHC_T)_k \times (V_{CD})_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    AC_{re} = \mathrm{PWF} \times A_{Tn} \left[
      \sum_{j=1}^{o} \left\{ (E_{Vi})_j \times (A_{Di})_j \times (WPI_{me})_j \right\}
      + \sum_{k=1}^{p} \left\{ (E_{VD})_k \times (A_{Ne})_k \times (WPI_{sp})_k \right\}
    \right]
    $}
    \]

  \item \textbf{Road user cost due to rerouting of vehicles during demolition at the end of life}
    \[ \mathrm{RUC}_{df} = \mathrm{VOC}_{df} + \mathrm{VOT}_{df} + \mathrm{AC}_{df} \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOC_{df} = \mathrm{PWF} \times D_{wm} \times DC_m \times RD \left[
      \sum_{j=1}^{o} \left\{ (C_{Ti})_j \times (V_{CD})_j \times (CF_T)_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (C_{Di})_k \times (V_{CD})_k \times (CF_D)_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    (Refer to table B-1 to B-16 to calculate distance and time related costs for VOC)
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    VOT_{df} = \mathrm{PWF} \times D_{wm} \times DC_m \times T_{AT} \left[
      \sum_{j=1}^{o} \left\{ (T_{VP})_j \times (V_{CD})_j \times (O_{Avg})_j \times (WPI_{Ti})_j \right\}
      + \sum_{k=1}^{p} \left\{ (CHC_T)_k \times (V_{CD})_k \times (WPI_{Di})_k \right\}
    \right]
    $}
    \]
    \[
    \resizebox{\linewidth}{!}{$\displaystyle
    AC_{df} = \mathrm{PWF} \times A_{Tn} \left[
      \sum_{j=1}^{o} \left\{ (E_{Vi})_j \times (A_{Di})_j \times (WPI_{me})_j \right\}
      + \sum_{k=1}^{p} \left\{ (E_{VD})_k \times (A_{Ne})_k \times (WPI_{sp})_k \right\}
    \right]
    $}
    \]
\end{itemize}

\vspace{0.3em}
\textbf{B.3.3 Environmental cost}

\textbf{Carbon Emission Cost}

\begin{itemize}[leftmargin=*]
  \item Carbon emission cost due to demolition and disposal for reconstruction
    \[ \mathrm{DR}_{\mathrm{EC}} = \mathrm{PWF} \times P_{\mathrm{IECd}} \]

  \item Carbon emission cost due to rerouting of vehicles during demolition for reconstruction
    \begin{align*}
    \mathrm{VEC}_{\mathrm{DR}}
    &= \mathrm{PWF} \times \mathrm{SCC} \times D_{wm} \times \mathrm{DC}_m \times \mathrm{RD} \\
    &\quad \times \sum_{k=1}^{p} (\mathrm{ADT})_k\, (\mathrm{EF}_v)_k
    \end{align*}

  \item Carbon emission cost due to reconstruction
    \[ \mathrm{REC}_{\mathrm{EC}} = \mathrm{PWF} \times \mathrm{IEC} \]

  \item Carbon emission cost due to rerouting of vehicles during reconstruction
    \begin{align*}
    \mathrm{VEC}_{\mathrm{REC}}
    &= \mathrm{PWF} \times \mathrm{SCC} \times D_{wm} \times \mathrm{DC}_m \times \mathrm{RD} \\
    &\quad \times \sum_{k=1}^{p} (\mathrm{ADT})_k\, (\mathrm{EF}_v)_k
    \end{align*}

  \item Carbon emission cost due to demolition and disposal at end of life
    \[ \mathrm{DF}_{\mathrm{EC}} = \mathrm{PWF} \times P_{\mathrm{IECd}} \]

  \item Carbon emission cost due to rerouting of vehicles during demolition at end of life
    \begin{align*}
    \mathrm{VEC}_{\mathrm{DF}}
    &= \mathrm{PWF} \times \mathrm{SCC} \times D_{wm} \times \mathrm{DC}_m \times \mathrm{RD} \\
    &\quad \times \sum_{k=1}^{p} (\mathrm{ADT})_k\, (\mathrm{EF}_v)_k
    \end{align*}
\end{itemize}



    """
        self.append(NoEscape(appendix_tex))
    def add_kv_table(self, caption, data, col1="10cm", col2="4.5cm"):
        """
        Add a two-column key-value table with caption.

        Args:
            caption (str): Table caption text
            data (dict): Key-value pairs to display
            col1 (str): Width of first column
            col2 (str): Width of second column
        """
        self.append(NoEscape(r"\vspace{4pt}"))
        self.append(NoEscape(r"\needspace{12\baselineskip}"))
        self.append(NoEscape(r"\noindent\captionof{table}{" + escape_latex(caption) + r"}"))
        self.append(NoEscape(r"\vspace{4pt}"))
        with self.create(Tabular(f"|p{{{col1}}}|p{{{col2}}}|")) as table:
            table.add_hline()
            for key, val in data.items():
                table.add_row([escape_latex(key), escape_latex(str(val))])
                table.add_hline()
        self.append(NoEscape(r"\vspace{4pt}"))

    # ==================================================================
    # METHOD: add_multi_table - Multi-column table with caption
    # ==================================================================
    def add_multi_table(self, caption, headers, data, col_spec):
        """
        Add a multi-column table with headers and caption.

        Args:
            caption (str): Table caption text
            headers (list): Column header strings
            data (dict): Key -> [values] mapping
            col_spec (str): LaTeX column specification
        """
        self.append(NoEscape(r"\vspace{4pt}"))
        self.append(NoEscape(r"\needspace{12\baselineskip}"))
        self.append(NoEscape(r"\noindent\captionof{table}{" + escape_latex(caption) + r"}"))
        self.append(NoEscape(r"\vspace{4pt}"))
        with self.create(Tabular(col_spec)) as table:
            table.add_hline()
            table.add_row([bold(h) for h in headers])
            table.add_hline()
            for key, vals in data.items():
                row = [escape_latex(key)] + [escape_latex(str(v)) for v in vals]
                table.add_row(row)
                table.add_hline()
        self.append(NoEscape(r"\vspace{4pt}"))

    # ==================================================================
    # METHOD: save_latex - Main entry point (matches CreateLatex API)
    # ==================================================================
    def save_latex(self, config, data, filename="LCCA_Report", output_dir=None):
        """
        Generate the LCCA PDF report.

        Args:
            config (dict): Boolean flags keyed by KEY_SHOW_* constants
            data (dict): Data dictionaries keyed by KEY_* constants
            filename (str): Output filename without extension
            output_dir (str): Directory to write the PDF into (defaults to CWD)
        """
        if config.get("show_introduction", True):
            self.add_introduction(config, data)
            self.append(NewPage())

        self.add_input_data(config, data)

        if config.get("show_lcca_results", True):
            self.append(NewPage())
            self.add_lcca_results(config, data)

        self.add_full_appendix()
        self.generate_pdf_output(filename, output_dir=output_dir)

    # ==================================================================
    # METHOD: add_introduction - Section 1: Introduction to LCCA
    # ==================================================================
    def add_introduction(self, config, data):
        """
        Add Section 1: Introduction to LCCA with framework figure.

        Args:
            config (dict): Config flags (unused for intro, reserved for future)
            data (dict): Must contain KEY_FRAMEWORK_FIGURE path
        """
        with self.create(Section("Introduction to LCCA")):
            self.append(
                NoEscape(
                    r"The life cycle cost is calculated using the 3PS-LCC approach, "
                    r"as illustrated in the figure below. Additional details about each "
                    r"component of this framework can be found at the following link. "
                    r"The components of the life-cycle cost analysis (LCCA) are also shown "
                    r"in the figure below. The assumptions adopted in the life-cycle cost "
                    r"calculations under this framework are listed in Appendix~A."
                )
            )

            # Figure 1-1
            fig_path = data.get(KEY_FRAMEWORK_FIGURE, "").replace("\\", "/")
            if os.path.exists(fig_path):
                self.append(NoEscape(r"\vspace{4pt}"))
                with self.create(Figure(position="H")) as fig:
                    fig.add_image(fig_path, width=NoEscape(r"\textwidth"))
                    fig.add_caption("3PS Life Cycle cost assessment")


    def add_input_data(self, config, data):
        """Section 2: Input Data - all 17 tables matching Word doc exactly."""
        with self.create(Section("Input data")):
            self.append(
                "This chapter provides general project information, including "
                "bridge configuration, analysis period, financial data and other "
                "inputs required for conducting life cycle cost assessment."
            )

            # ── 2.1 Bridge geometry ──────────────────────────────────────────
            with self.create(Subsection("Bridge geometry and description")):
                self.append(
                    "Details of bridge type, span length, number of spans, "
                    "and functional classification."
                )
                if config.get(KEY_SHOW_BRIDGE_DESC, True):
                    self.add_kv_table(
                        "Bridge description",
                        data.get(KEY_BRIDGE_DESC, {}),
                        col1="9cm", col2="5.5cm",
                    )

            # ── 2.2 User note ────────────────────────────────────────────────
            with self.create(Subsection("User note")):
                if config.get(KEY_SHOW_FINANCIAL, True):
                    self.add_kv_table(
                        "Financial Data",
                        data.get(KEY_FINANCIAL, {}),
                        col1="7.5cm", col2="7cm",
                    )

            # ── 2.3 Construction data ────────────────────────────────────────
            with self.create(Subsection("Construction data")):
                self.append("Material quantities and unit rates.")

                # Table 2-3: 6 columns - Category | Material | Quantity | Unit | Rate | Source
                # One longtable per structural category (Foundation, Sub Structure, etc.)
                if config.get(KEY_SHOW_CONSTRUCTION, True):
                    construction = data.get(KEY_CONSTRUCTION, {})
                    cat_table_captions = {
                        "Foundation":     "Construction material quantities and rates for foundation",
                        "Sub Structure":  "Construction material quantities and rates for substructure",
                        "Super Structure":"Construction material quantities and rates for superstructure",
                        "Miscellaneous":  "Construction material quantities and rates for miscellaneous activities",
                    }
                    col_spec = (
                        r"|>{\raggedright\arraybackslash}p{2.0cm}"
                        r"|>{\raggedright\arraybackslash}p{4.0cm}"
                        r"|>{\raggedright\arraybackslash}p{1.6cm}"
                        r"|>{\raggedright\arraybackslash}p{1.2cm}"
                        r"|>{\raggedright\arraybackslash}p{2.2cm}"
                        r"|>{\raggedright\arraybackslash}p{2.4cm}|"
                    )
                    header_row = (
                        r"\textbf{Category} & \textbf{Material}"
                        r" & \textbf{Rate} & \textbf{Quantity}"
                        r" & \textbf{Unit} & \textbf{Source} \\"
                    )

                    for cat_name, components in construction.items():
                        caption = cat_table_captions.get(
                            cat_name,
                            f"Construction material quantities and rates for {cat_name.lower()}"
                        )
                        self.append(NoEscape(r"\vspace{4pt}"))
                        self.append(NoEscape(r"\needspace{8\baselineskip}"))

                        # Build longtable rows
                        rows_tex = ""
                        for comp_name, mat_rows in components.items():
                            row_count = len(mat_rows)
                            for idx, row_vals in enumerate(mat_rows):
                                from pylatex.utils import escape_latex as el
                                # row_vals: [mat, qty, unit, rate, source_display, db_modified]
                                mat         = row_vals[0]
                                qty         = row_vals[1]
                                unit        = row_vals[2]
                                rate        = row_vals[3]
                                source      = row_vals[4]
                                db_modified = row_vals[5] if len(row_vals) > 5 else False

                                if idx == 0:
                                    cat_cell = (
                                        r"\multirow{" + str(row_count) + r"}{*}"
                                        r"{\parbox[t]{1.9cm}{\raggedright\footnotesize\textbf{"
                                        + el(comp_name) + r"}}}"
                                    )
                                else:
                                    cat_cell = ""

                                # Light green cell if rate was modified from DB
                                if db_modified:
                                    source_cell = r"\cellcolor[HTML]{90EE90}" + el(source)
                                else:
                                    source_cell = el(source)

                                cells = [
                                    cat_cell,
                                    el(mat),
                                    el(rate),
                                    el(qty),
                                    el(unit),
                                    source_cell,
                                ]
                                rows_tex += " & ".join(cells) + r" \\" + "\n"

                                if idx < row_count - 1:
                                    rows_tex += r"\cline{2-6}" + "\n"
                                else:
                                    rows_tex += r"\hline" + "\n"

                        # Caption is placed INSIDE longtable so the counter increments only once
                        caption_tex = r"\caption{" + escape_latex(caption) + r"}\\" + "\n"

                        longtable_tex = (
                            r"{\footnotesize" + "\n"
                            + r"\begin{longtable}{" + col_spec + r"}" + "\n"
                            + caption_tex
                            + r"\hline" + "\n"
                            + header_row + "\n"
                            + r"\hline" + "\n"
                            + r"\endfirsthead" + "\n"
                            + r"\hline" + "\n"
                            + header_row + "\n"
                            + r"\hline" + "\n"
                            + r"\endhead" + "\n"
                            + r"\endfoot" + "\n"
                            + r"\hline" + "\n"
                            + r"\endlastfoot" + "\n"
                            + rows_tex
                            + r"\end{longtable}" + "\n"
                            + r"}"
                        )
                        self.append(NoEscape(longtable_tex))
                        self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-4: 3 columns - row | Assumed % | Basis
                if config.get(KEY_SHOW_LCC_ASSUMPTIONS, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Assumptions for different "
                        r"life cycle cost components}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{5.5cm}|p{3cm}|p{5cm}|")) as t:
                        t.add_hline()
                        t.add_row(["", bold("Assumed percentage"), ""])
                        t.add_hline()
                        for key, vals in data.get(KEY_LCC_ASSUMPTIONS, {}).items():
                            t.add_row([escape_latex(key),
                                       escape_latex(str(vals[0])),
                                       escape_latex(str(vals[1]))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-5: 2-column kv
                if config.get(KEY_SHOW_USE_STAGE, True):
                    self.add_kv_table(
                        "Details related to duration and interval of use stage activities",
                        data.get(KEY_USE_STAGE, {}),
                        col1="10cm", col2="4.5cm",
                    )

            # ── 2.4 Traffic data ─────────────────────────────────────────────
            with self.create(Subsection("Traffic data")):
                self.append(
                    "Average daily traffic by vehicle class, rerouting distance, "
                    "construction duration, vehicle operating cost and value of "
                    "time parameters."
                )

                # Table 2-9: Vehicle type | Vehicles/day
                if config.get(KEY_SHOW_AVG_TRAFFIC, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{12\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Average Daily Traffic for each vehicle}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{10cm}|p{4.5cm}|")) as t:
                        t.add_hline()
                        t.add_row([bold("Vehicle type"), bold("Vehicles/day")])
                        t.add_hline()
                        for key, val in data.get(KEY_AVG_TRAFFIC, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-10: Road and traffic related data (2-col kv)
                if config.get(KEY_SHOW_ROAD_TRAFFIC, True):
                    self.add_kv_table(
                        "Road and traffic related data",
                        data.get(KEY_ROAD_TRAFFIC, {}),
                        col1="9cm", col2="5.5cm",
                    )

                # Table 2-11: Peak hour distribution
                if config.get(KEY_SHOW_PEAK_HOUR, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Peak hour distribution}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{7cm}|p{7.5cm}|")) as t:
                        t.add_hline()
                        t.add_row([bold("Hour Category"), bold("Traffic proportion")])
                        t.add_hline()
                        for key, val in data.get(KEY_PEAK_HOUR, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-12: Human injury cost data - 2 cols
                if config.get(KEY_SHOW_HUMAN_INJURY, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Human injury cost data}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{7cm}|p{7.5cm}|")) as t:
                        t.add_hline()
                        t.add_row([
                            bold("Category of accident"),
                            NoEscape(r"\textbf{Accident distribution (\%)}"),
                        ])
                        t.add_hline()
                        for key, val in data.get(KEY_HUMAN_INJURY, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-13: Vehicle damage cost data - 2 cols
                if config.get(KEY_SHOW_VEHICLE_DAMAGE, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{12\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Vehicle damage cost data}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{7cm}|p{7.5cm}|")) as t:
                        t.add_hline()
                        t.add_row([
                            bold("Vehicle type"),
                            NoEscape(r"\textbf{Percentage of accidents for each vehicle type}"),
                        ])
                        t.add_hline()
                        for key, val in data.get(KEY_VEHICLE_DAMAGE, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

            # ── 2.5 Environmental input data ─────────────────────────────────
            with self.create(Subsection("Environmental input data")):
                self.append(
                    "Emission factors for construction and traffic activities "
                    "and carbon pricing assumptions."
                )

                # Table 2-13: Social Cost of Carbon - 2-col kv
                if config.get(KEY_SHOW_SOCIAL_CARBON, True):
                    self.add_kv_table(
                        "Social Cost of Carbon",
                        data.get(KEY_SOCIAL_CARBON, {}),
                        col1="9cm", col2="5.5cm",
                    )

                # Table 2-15: 7 cols - Category | Material | Qty | Unit | CF | EF | EF unit
                if config.get(KEY_SHOW_MATERIAL_EMISSION, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Material related factors for emission}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"{\footnotesize"))
                    with self.create(Tabular(
                        "|p{2.2cm}|p{3.2cm}|p{1.3cm}|p{1.0cm}|p{1.8cm}|p{1.8cm}|p{2.0cm}|"
                    )) as t:
                        t.add_hline()
                        t.add_row([
                            bold("Category"),
                            bold("Material"),
                            bold("Quantity"),
                            bold("Unit"),
                            bold("Conversion factor"),
                            bold("Emission factor"),
                            NoEscape(r"\textbf{Emission factor unit}"),
                        ])
                        t.add_hline()
                        for mat, vals in data.get(KEY_MATERIAL_EMISSION, {}).items():
                            # vals: [category, qty, unit, cf, ef, ef_unit]
                            category = escape_latex(str(vals[0])) if len(vals) > 0 else ""
                            row = [category, escape_latex(mat)] + [escape_latex(str(v)) for v in vals[1:]]
                            t.add_row(row)
                            t.add_hline()
                    self.append(NoEscape(r"}"))
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-15: 2 cols - row | Assumed % of initial emission
                if config.get(KEY_SHOW_USE_EMISSION, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Assumptions for use stage "
                        r"and end of life emissions}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{9cm}|p{5cm}|")) as t:
                        t.add_hline()
                        t.add_row(["",
                                   bold("Assumed \\% of initial emission")])
                        t.add_hline()
                        for key, val in data.get(KEY_USE_EMISSION, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-16: Vehicle | Emission factor
                if config.get(KEY_SHOW_VEHICLE_EMISSION, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{12\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Vehicle related emission factors}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    with self.create(Tabular("|p{9cm}|p{5cm}|")) as t:
                        t.add_hline()
                        t.add_row([bold("Vehicle type"), bold("Emission factor")])
                        t.add_hline()
                        for key, val in data.get(KEY_VEHICLE_EMISSION, {}).items():
                            t.add_row([escape_latex(key), escape_latex(str(val))])
                            t.add_hline()
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-17: 8 cols - emissions from transportation of material (NEW)
                if config.get(KEY_SHOW_TRANSPORT_EMISSION, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Data for emissions related to "
                        r"transportation of material}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"{\footnotesize"))
                    with self.create(Tabular(
                        "|p{2.0cm}|p{2.0cm}|p{1.3cm}|p{1.5cm}|p{1.5cm}|p{1.5cm}|p{1.5cm}|p{2.1cm}|"
                    )) as t:
                        t.add_hline()
                        t.add_row([
                            bold("Transport Material"),
                            bold("Vehicle name"),
                            NoEscape(r"\textbf{GVW (tonne)}"),
                            NoEscape(r"\textbf{Cargo capacity (tonne)}"),
                            NoEscape(r"\textbf{Distance travelled (km)}"),
                            bold("Source"),
                            bold("Destination"),
                            NoEscape(r"\textbf{Emission Factor (kgCO\textsubscript{2}e/tonne-km)}"),
                        ])
                        t.add_hline()
                        for mat, vals in data.get(KEY_TRANSPORT_EMISSION, {}).items():
                            t.add_row([escape_latex(mat)] +
                                      [escape_latex(str(v)) for v in vals])
                            t.add_hline()
                    self.append(NoEscape(r"}"))
                    self.append(NoEscape(r"\vspace{4pt}"))

                # Table 2-18: 6 cols on-site emissions (Emissions column removed per updated template)
                if config.get(KEY_SHOW_ONSITE_EMISSION, True):
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"\needspace{8\baselineskip}"))
                    self.append(NoEscape(
                        r"\noindent\captionof{table}{Emissions from on-site "
                        r"activities during construction}"
                    ))
                    self.append(NoEscape(r"\vspace{4pt}"))
                    self.append(NoEscape(r"{\footnotesize"))
                    with self.create(Tabular(
                        "|p{2.8cm}|p{2.0cm}|p{2.3cm}|p{1.5cm}|p{1.8cm}|p{2.3cm}|"
                    )) as t:
                        t.add_hline()
                        t.add_row([
                            bold("Construction Equipment"),
                            bold("Energy Source"),
                            NoEscape(r"\textbf{Diesel consumption (l/hour) or Electricity (Kw)}"),
                            NoEscape(r"\textbf{Avg number of hours used per day}"),
                            NoEscape(r"\textbf{Number of days the equipment would be used}"),
                            NoEscape(r"\textbf{Emission factor (kgCO\textsubscript{2}e/unit)}"),
                        ])
                        t.add_hline()
                        for equip, vals in data.get(KEY_ONSITE_EMISSION, {}).items():
                            # Support both 5-value (new, no emissions col) and 6-value (legacy) data
                            row_vals = list(vals)[:5]
                            t.add_row([escape_latex(equip)] +
                                      [escape_latex(str(v)) for v in row_vals])
                            t.add_hline()
                    self.append(NoEscape(r"}"))
                    self.append(NoEscape(r"\vspace{4pt}"))

    def generate_pdf_output(self, filename="LCCA_Report", output_dir=None):

        print("[INFO]: Generating report...")
        import os as _os
        _orig_cwd = _os.getcwd()
        try:
            if output_dir:
                _os.makedirs(output_dir, exist_ok=True)
                _os.chdir(output_dir)
            self.generate_pdf(
                filename,
                clean_tex=False,
                compiler="pdflatex",
                compiler_args=["-interaction=nonstopmode"],
            )
            print(f"[INFO]: Done -> {filename}.pdf")
        except Exception as e:
            print(f"[ERROR]: PDF compile issue: {e}")
            self.generate_tex(filename)
            print(f"[INFO]: TeX saved -> {filename}.tex")
            print(f"[INFO]: Run: pdflatex {filename}.tex")
        finally:
            _os.chdir(_orig_cwd)
            print(f"[INFO]: Run: pdflatex {filename}.tex")




def generate_report(output_filename="LCCA_Report", input_json=None, config_override=None, output_dir=None):
    """
    Wrapper that reads a .3psLCCA JSON file via LCCATemplate and calls save_latex().

    Args:
        output_filename (str): Output PDF filename without extension
        input_json (str): Path to the .3psLCCA JSON file
        config_override (dict): Optional {KEY_SHOW_*: bool} to override defaults
        output_dir (str): Directory to write the PDF into (defaults to CWD)
    """
    if not input_json or not os.path.exists(input_json):
        raise FileNotFoundError(
            f"[ERROR]: JSON file not found: {input_json}\n"
            "Usage: python lcca_generate.py --json LCC_Report.3psLCCA --out LCCA_Report"
        )

    print(f"[INFO]: Loading data from JSON: {input_json}")

    # Load all data and config from the .3psLCCA JSON via LCCATemplate
    tmpl   = LCCATemplate(input_json)
    config = tmpl.get_config()
    data   = tmpl.get_report_data()

    # Apply programmatic config override (e.g. from GUI)
    if config_override is not None:
        config.update(config_override)

    # Create report and generate
    doc = LCCAReportLatex()
    doc.save_latex(config, data, output_filename, output_dir=output_dir)






# ==============================================================================
# MAIN - CLI entry point
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate LCCA Report")
    parser.add_argument("--json", type=str, default="LCC_Report.3psLCCA", help="Path to .3psLCCA JSON file")
    parser.add_argument(
        "--out",
        type=str,
        default="LCCA_Report",
        help="Output PDF filename (without extension)",
    )
    args = parser.parse_args()

    generate_report(args.out, input_json=args.json)
