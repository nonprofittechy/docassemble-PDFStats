# pre-load

import os
import re
import json
import uuid
from hashlib import sha256

import textstat
import pandas
from flask import Blueprint, flash, request, redirect, url_for, current_app
from werkzeug.utils import secure_filename

import formfyxer
from formfyxer import lit_explorer

try:
  from docassemble.webapp.app_object import csrf
  from docassemble.base.util import get_config
except:
  csrf = type('', (), {})
  # No-op decorator
  csrf.exempt = lambda func: func
  def get_config(var):
      return current_app.config.get(var.replace(" ", "_").upper())

bp = Blueprint('pdfstats', __name__, url_prefix='/pdfstats')

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'pdf'}

current_app.config['PDFSTAT_UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def valid_uuid(file_id):
    return bool(re.match(r"^[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}$", file_id))

def valid_hash(hash):
    return bool(re.match(r"^[A-Fa-f0-9]{64}$", hash))

def minutes_to_hours(minutes:float)->str:
  if minutes < 2:
    return "1 minute"
  if minutes > 60:
    res = divmod(minutes, 60)
    return f"{res[0]} hour{'s' if res[0] > 1 else ''} and { res[1] } minute{'s' if res[1] > 1 or res[1] < 1 else ''}"
  else:
    return f"{minutes} minute{'s' if minutes > 1 else ''}"

upload_form = '''
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Upload PDF</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-iYQeCzEYFbKjA/T2uDLTpkwGzCiq6soy8tYaI1GyVh/UjpbCx/TYkiZhlZB6+fzT" crossorigin="anonymous">
    <style>
    .suffolk-blue {
        background-color: #002e60;
    }
    .upload-centered {
        width: 100%;
        max-width: 330px;
        padding: 15px;
        margin: auto;
    }
    </style>
  </head>
<body class="text-center">
<nav class="navbar navbar-dark suffolk-blue">
  <div class="container-fluid">
    <a class="navbar-brand" href="https://suffolklitlab.org">
  <img src="https://apps.suffolklitlab.org/packagestatic/docassemble.MassAccess/lit_logo_light.png?v=0.3.0" alt="Logo" width="30" height="24" class="d-inline-block align-text-top"/>
  Suffolk LIT Lab
  </a>
  </div>
</nav>    
<main class="upload-centered">
    <form method=post enctype=multipart/form-data>
    <h1 class="h3 mb-3 fw-normal">Upload a PDF</h1>

    <div>
        <label for="file" class="form-label">PDF file</label>
        <input class="form-control form-control-md" id="file" name="file" type="file">
    </div>    

        <button type="submit" class="btn btn-primary mb-3 mt-3">Upload file</button>
  </form>
</main>
</body>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/js/bootstrap.bundle.min.js" integrity="sha384-u1OknCvxWvY5kfmNBILK2hRnQC3Pr17a+RTT6rIHI7NnikvbZlHgTPOOmMi466C8" crossorigin="anonymous"></script>
</html>
    '''

@bp.route('/', methods=['GET', 'POST'])
@csrf.exempt
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_content = file.read()
            intermediate_dir = str(sha256(file_content).hexdigest()) # str(uuid.uuid4())
            to_path = os.path.join(current_app.config['PDFSTAT_UPLOAD_FOLDER'], intermediate_dir)
            if os.path.isdir(to_path):
                if os.path.isfile(os.path.join(to_path, "stats.json")):
                    return redirect(url_for("pdfstats.view_stats", file_hash=intermediate_dir))
            else:
                os.mkdir(to_path)
            full_path = os.path.join(to_path, filename)
            with open(full_path, "wb") as write_file:
                write_file.write(file_content)
            stats = formfyxer.parse_form(full_path, normalize=True, debug=True, openai_creds=get_config("open ai"), spot_token=get_config("spot token"))
            with open(os.path.join(to_path, "stats.json"), "w") as stats_file:
                stats_file.write(json.dumps(stats))
            return redirect(url_for('pdfstats.view_stats', file_hash=intermediate_dir))
    return upload_form

from flask import send_from_directory

def get_pdf_from_dir(file_hash):
    path_to_dir = os.path.join(
        current_app.config["PDFSTAT_UPLOAD_FOLDER"],
        secure_filename(file_hash),
    )
    for f in os.listdir(path_to_dir):
        if f.endswith(".pdf"):
            return f
    return None


@bp.route('/download/<file_hash>')
def download_file(file_hash):
    if not (file_hash and valid_hash(file_hash)):
        raise Exception ("Not a valid filename")
    f = get_pdf_from_dir(file_hash)
    if f:
        return send_from_directory(directory=current_app.config["PDFSTAT_UPLOAD_FOLDER"], path=os.path.join(file_hash, f))
    raise Exception("No file uploaded here")


@bp.route('/view/<file_hash>')
def view_stats(file_hash):
    if not (file_hash and valid_hash(file_hash)):
        raise Exception("Not a valid filename")
    to_dir = os.path.join(current_app.config["PDFSTAT_UPLOAD_FOLDER"], file_hash)
    with open(os.path.join(to_dir, "stats.json")) as stats_file:
        stats = json.loads(stats_file.read())
    metric_means = {
      "complexity score": 18.25398487,
      "time to answer": 49.266632,
      "reading grade level": 7.180685,
      "pages": 2.2601246,
      "total fields": 38.38878,
      "avg fields per page": 20.98784,
      "number of sentences": 71.4894,
      "difficult word count": 75.675389408,
      "difficult word percent": 0.127301677,
      "number of passive voice sentences": 8.11557632,
      "sentences per page": 31.25462694,
      "citation count": 1.098442367
    }
    metric_stddev = {
      "complexity score": 5.86058205587,
      "time to answer": 82.79478559926,
      "reading grade level": 1.561731,
      "pages": 1.97868674,
      "total fields": 47.211886658,
      "avg fields per page": 20.96440214,
      "number of sentences": 83.419848187,
      "difficult word count": 75.67538940809969,
      "difficult word percent": 0.03873129,
      "sentences per page": 14.38664529,
      "number of passive voice sentences": 10.843292156557,
      "citation count": 4.122761536011
    }

    def get_class(k, val=None):
      if val is None:
        val = stats.get(k, metric_means[k])

      if val < metric_means[k] - metric_stddev[k]:
        return "data-good"
      if val < metric_means[k] + metric_stddev[k]:
        return ""
      if val < metric_means[k] + 2 * metric_stddev[k]:
        return "data-warn"
      return "data-bad"

    def get_data(k):
      return f'<font size="1">Mean: {metric_means[k]:.2f}, Std. {metric_stddev[k]:.2f}</font>'

    title = stats.get('title', file_hash)
    complexity_score = formfyxer.form_complexity(stats)
    word_count = len(stats.get("text").split(" "))
    difficult_word_count = textstat.difficult_words(stats.get("text"))
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stats for { title }</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-iYQeCzEYFbKjA/T2uDLTpkwGzCiq6soy8tYaI1GyVh/UjpbCx/TYkiZhlZB6+fzT" crossorigin="anonymous">
    <style>
    .suffolk-blue {{
        background-color: #002e60;
    }}
    .data-good {{
        background-color: #66ff66;
    }}
    .table .data-good:before {{
        content: "☑️"
    }}
    .data-warn {{
        background-color: #fdfd66;
    }}
    .table .data-warn:before {{
        content: "⚠️"
    }}
    .table .data-bad {{
        background-color: #ef6161;
    }}
    .data-bad:before {{
        content: "❌"
    }}
    a.btn-primary {{
        margin-left: auto;
        margin-right: auto;
        display: block;
        width: 175px;
    }}
    </style>
  </head>
<body>
<nav class="navbar navbar-dark suffolk-blue">
  <div class="container-fluid">
    <a class="navbar-brand" href="https://suffolklitlab.org">
  <img src="https://apps.suffolklitlab.org/packagestatic/docassemble.MassAccess/lit_logo_light.png?v=0.3.0" alt="Logo" width="30" height="24" class="d-inline-block align-text-top"/>
  Suffolk LIT Lab
  </a>
  </div>
</nav>

<main style="max-width: 800px; margin-left: auto; margin-right: auto; padding-left: 8px;">
<h1 class="pb-2 border-bottom text-center">File statistics for <span class="text-break">{ title }</span></h1>
<p>
<a class="btn btn-primary" href="/pdfstats/download/{file_hash}" role="button">Download the file</a>
</p>
<br/>
<table class="table text-center">
    <thead>
    <tr>
      <th scope="col">Statistic name</th>
      <th scope="col">Value</th>
      <th scope="col">Target + Compare</th>
    </tr>
    </thead>
    <tbody>
    <tr>
    <th scope="row">Complexity Score</th>
    <td class="{get_class("complexity score", complexity_score)}">{ "{:.2f}".format(complexity_score) }</td>
    <td>{get_data("complexity score")}<br/>Lower is better, see <a href="#flush-collapseFour">the footnotes</a> for more information.</td>
    </tr>
    <tr>
    <th scope="row">Time to read</th>
    <td>
    About { minutes_to_hours(int(word_count / 150)) }
    </td>
    <td>Assuming 150 words per minute reading speed.</td>
    </tr>
    <tr>
    <th scope="row">Time to answer</th>
    <td class="{get_class("time to answer", stats.get("time to answer", (0,0))[0])}">
    About { minutes_to_hours(round(stats.get("time to answer", (0,0))[0])) }, plus or minus { minutes_to_hours(round(stats.get("time to answer", (0,0))[1])) }
    </td>
    <td>The variation covers 1 standard deviation. See <a href="#flush-collapseThree">the footnotes</a> for more information.</td>
    </tr>
    <tr>
    <th scope="row">
    Consensus reading grade level
    </th>
    <td class="{get_class("reading grade level")}">Grade { int(stats.get("reading grade level")) }</td>
    <td>Target is <a href="https://suffolklitlab.org/docassemble-AssemblyLine-documentation/docs/style_guide/readability#target-reading-level">4th-6th grade</a><br/>{get_data("reading grade level")}</td>
    </tr>
    <tr>
    <th scope="row">
    Number of pages
    </th>
    <td class="{get_class("pages")}">{ stats.get("pages") }</td>
    <td>{get_data("pages")}</td>
    </tr>
    <tr>
    <th scope="row">
    Number of fields
    </th>
    <td class="{get_class("total fields")}">{ len(stats.get("fields",[])) }</td>
    <td>{get_data("total fields")}</td>    
    </tr>
    <tr>
    <th scope="row">
    Average number of fields per page
    </th>
    <td class="{get_class("avg fields per page")}">{float(stats.get("avg fields per page",0)):.1f}</td>
    <td>Target is < 15<br/>{get_data("avg fields per page")}</td>
    </tr>
    <tr>
    <th scope="row">
    Number of sentences per page
    </th>
    <td class="{get_class("sentences per page")}">{ stats.get("sentences per page") }</td>
    <td>{get_data("sentences per page")}</td>
    </tr>
    <tr>
    <th scope="row">
    Word count
    </th>
    <td>{ word_count } ({float(word_count/stats.get("pages",1.0)):.1f} per page)</td>
    <td>Users <a href="https://www.nngroup.com/articles/how-little-do-users-read/">read as little as 20% of the content</a> on a longer page. Try to keep word count to 110 words.</td>
    </tr>
    <tr>
    <th scope="row">
    Number of "difficult words"
    </th>
    <td class="{get_class("difficult word percent")}">{ difficult_word_count } <br/> ({stats.get("difficult word percent"):.1f}%)</td>
    <td>May include inflections of some "easy" words. Target is < 5% <br/>{get_data("difficult word percent")}</td>
    </tr>
    <tr>
    <th scope="row">
    Percent of sentences with passive voice
    </th>
    <td>{stats.get("number of passive voice sentences",0) / stats.get("number of sentences",1) * 100:.1f}%</td>
    <td>Target is < 5%</td>
    </tr>
    <tr>
    <th scope="row">
    Number of citations
    </th>
    <td class="{get_class("citation count")}">{ len(stats.get("citations",[])) }</td>
    <td>Avoid using citations in court forms.<br/>{get_data("citation count")}</td>
    </tr>
    </tbody>
</table>

<h2 class="pb-2 border-bottom text-center">Ideas for Improvements</h2>

{ "<p>Here's an idea for a new title*: <b>" + stats["suggested title"] + "</b></p>" if stats.get("suggested title") else ""}

<p>Here's a idea for an easy-to-read description of the form*:
<div class="card text-left">
  <div class="card-body">
   { stats["description"] }
  </div>
</div>
</p>


<div class="accordion text-center" id="fullTextAccordion">
  <div class="accordion-item">
    <h2 class="accordion-header" id="flush-headingOne">
      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#flush-collapseOne" aria-expanded="false" aria-controls="flush-collapseOne">
        Full text of form
      </button>
    </h2>
    <div id="flush-collapseOne" class="accordion-collapse collapse" aria-labelledby="flush-headingOne" data-bs-parent="#fullTextAccordion">
      <div class="accordion-body">
        { stats.get("text") }
      </div>
    </div>
  </div>
  <div class="accordion-item">
    <h2 class="accordion-header" id="flush-headingTwo">
      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#flush-collapseTwo" aria-expanded="false" aria-controls="flush-collapseTwo">
        Citations
      </button>
    </h2>
    <div id="flush-collapseTwo" class="accordion-collapse collapse" aria-labelledby="flush-headingTwo" data-bs-parent="#fullTextAccordion">
      <div class="accordion-body">
        { "<br/>".join(stats.get("citations",[])) }
      </div>
    </div>
  </div>
  <div class="accordion-item">
    <h2 class="accordion-header" id="flush-headingThree">
      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#flush-collapseThree" aria-expanded="false" aria-controls="flush-collapseThree">
        Information about fields
      </button>
    </h2>
    <div id="flush-collapseThree" class="accordion-collapse collapse" aria-labelledby="flush-headingThree" data-bs-parent="#fullTextAccordion">
      <div class="accordion-body">
      <p><b>Note: "time to answer" is drawn as a random sample from an assumed normal distribution of times to answer, with a pre-set standard deviation and mean that depends
      on the answer type and allowed number of characters. It will likely be a different number if you refresh and recalculate.</b></p>
      { pandas.DataFrame.from_records(stats.get("debug fields")).to_html() if stats.get("debug fields") else [] }
      </div>
    </div>
  </div>
  <div class="accordion-item">
    <h2 class="accordion-header" id="flush-headingFour">
      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#flush-collapseFour" aria-expanded="false" aria-controls="flush-collapseFour">
        Information about complexity
      </button>
    </h2>
    <div id="flush-collapseFour" class="accordion-collapse collapse" aria-labelledby="flush-headingFour" data-bs-parent="#fullTextAccordion">
      <div class="accordion-body">
      <p><b>Note: this is a list of each metric and its specific score; they are summed together to get the total score</b></p>
      <table class="table">
      <thead>
        <tr>
          <th>Metric name</th>
          <th>Original value</th>
          <th>Weighted value</th>
        </tr>
      </thead>
      <tbody>
        { chr(10).join(['<tr><th scope="row">{}</th><td>{:.2f}</td><td>{:.2f}</td></tr>'.format(v[0], v[1], v[2]) for v in lit_explorer._form_complexity_per_metric(stats)]) }
      </tbody>
      </table>
      </div>
    </div>
  </div>

</div>
<br/>


<a class="btn btn-primary" href="/pdfstats" role="button">Upload a new PDF</a>


<br/>

<p>Feedback? Email <a href="mailto:massaccess@suffolk.edu">massaccess@suffolk.edu</a></p>

<br/>

<p>*: These suggestions are provided by <a href="https://openai.com/blog/gpt-3-apps/">OpenAI's GPT3</a>.</p>

</main>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.3/jquery.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/js/bootstrap.bundle.min.js" integrity="sha384-u1OknCvxWvY5kfmNBILK2hRnQC3Pr17a+RTT6rIHI7NnikvbZlHgTPOOmMi466C8" crossorigin="anonymous"></script>
    <script>
    (function($){{
        $(document).ready(function() {{
            var accordSec = window.location.hash;
            if (accordSec.length) {{
                $(accordSec).collapse("show");
            }}
        }});
     }})(jQuery);
    </script>
</body>

</html>
    """

try:
  from docassemble.webapp.app_object import app
  app.register_blueprint(bp)
except:
  pass
