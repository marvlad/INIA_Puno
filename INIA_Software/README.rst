How to run the report generator
===============================

The main program is executed from the command line using ``main.py``.

Basic command
-------------

.. code-block:: bat

   python main.py --resultados-excel "RESULTADOS.xlsx" --template-excel "TEMPLATE.xlsx" --name "PERSON NAME" --cultivo "CULTIVO" --report-root "OUTPUT_FOLDER" --pdf-folder "PDF_FOLDER" --report-script "report_pdf.py"

Example
-------

.. code-block:: bat

   python main.py --resultados-excel "RESULTADOS USUARIOS.xlsx" --template-excel "Software_Mejorado_Cultivos.xlsx" --name "Huaman Huaman Arturo" --cultivo "COL" --report-root "REPORTES_GENERADOS" --pdf-folder "INFORMES DE ENSAYO" --report-script "report_pdf.py"

Arguments
---------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Argument
     - Description
   * - ``--resultados-excel``
     - Excel file containing the user/sample data.
   * - ``--template-excel``
     - Excel template used to generate the filled report.
   * - ``--name``
     - Name of the person/sample owner to search for in the results Excel file.
   * - ``--cultivo``
     - Crop used for the fertilization recommendation. Example: ``COL``, ``PAPA``, ``QUINUA``.
   * - ``--report-root``
     - Folder where the generated report files will be saved.
   * - ``--pdf-folder``
     - Folder containing the original laboratory PDF reports. The script searches and copies the matching SU PDF.
   * - ``--report-script``
     - Python script used to generate the final PDF report.

Notes for Windows
-----------------

Use quotation marks around file names or folders that contain spaces.

Example:

.. code-block:: bat

   --resultados-excel "RESULTADOS USUARIOS.xlsx"

Use quotation marks around names too.

Example:

.. code-block:: bat

   --name "Huaman Huaman Arturo"

Output
------

After running successfully, the program creates a report folder inside the selected ``--report-root`` directory.

The generated folder may contain:

.. code-block:: text

   filled Excel file
   generated PDF report
   copied matching SU PDF
   intermediate files used during report generation

Common problems
---------------

Python is not recognized
~~~~~~~~~~~~~~~~~~~~~~~~

Use ``py`` instead of ``python``:

.. code-block:: bat

   py main.py --resultados-excel "RESULTADOS.xlsx" --template-excel "TEMPLATE.xlsx" --name "PERSON NAME" --cultivo "CULTIVO" --report-root "OUTPUT_FOLDER" --pdf-folder "PDF_FOLDER" --report-script "report_pdf.py"

File not found
~~~~~~~~~~~~~~

Check that the input files exist and that file names or folders with spaces are inside quotation marks.

Person not found
~~~~~~~~~~~~~~~~

Make sure the value passed to ``--name`` matches the name in the results Excel file.

Crop not available
~~~~~~~~~~~~~~~~~~

Make sure the value passed to ``--cultivo`` is included in the allowed product list.
