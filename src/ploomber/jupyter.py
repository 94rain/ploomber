"""
Module for the jupyter extension
"""
from jupytext.contentsmanager import TextFileContentsManager
from ploomber.sources.NotebookSource import (_cleanup_rendered_nb,
                                             inject_cell)
from ploomber.spec.DAGSpec import DAGSpec
from ploomber.exceptions import DAGSpecInitializationError


class PloomberContentsManager(TextFileContentsManager):
    """
    Ploomber content manager subclasses jupytext TextFileContentsManager
    to keep jupytext features of opening .py files as notebooks but adds
    a feature that automatically injects parameters in notebooks if they
    are part of a pipeline defined in pipeline.yaml, these injected parameters
    are deleted before saving the file
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the content manger, look for a pipeline.yaml file in the
        current directory, if there is one, load it, if there isn't one
        don't do anything
        """
        import sys
        sys.path.append('')

        # try to automatically locate the dag spec
        dag = DAGSpec.auto_load()

        if dag:
            dag.render()
            self._dag = dag
            self._dag_mapping = {str(t.source.loc): t for t in dag.values()}
            self.log.info('[Ploomber] Initialized Ploomber DAG from '
                          'pipeline.yaml...')
        else:
            # no pipeline.yaml found...
            self.log.info('[Ploomber] No pipeline.yaml found, skipping DAG '
                          'initialization...')
            self._dag = None
            self._dag_mapping = None

        return super(PloomberContentsManager, self).__init__(*args, **kwargs)

    def get(self, *args, **kwargs):
        """
        This is called when a file/directory is requested (even in the list
        view)
        """
        model = super(PloomberContentsManager, self).get(*args, **kwargs)

        if self._model_in_dag(model):
            self.log.info('[Ploomber] Injecting cell...')
            inject_cell(model=model,
                        params=self._dag_mapping[model['path']]._params)

        return model

    def save(self, model, path=""):
        """
        This is called when a file is saved
        """
        if self._model_in_dag(model):
            self.log.info('[Ploomber] Cleaning up injected cell in {}...'
                          .format(model['name']))
            _cleanup_rendered_nb(model['content'])

        return super(PloomberContentsManager, self).save(model, path)

    def _model_in_dag(self, model):
        """Determine if the model is part of the  pipeline
        """
        model_in_dag = False

        if self._dag:
            if (model['content'] and model['type'] == 'notebook'):
                if model.get('path') in self._dag_mapping:
                    # NOTE: not sure why sometimes the model comes with a
                    # names and sometimes it doesn't
                    self.log.info('[Ploomber] {} is part of the pipeline... '
                                  .format(model.get('name') or ''))
                    model_in_dag = True
                else:
                    self.log.info('[Ploomber] {} is not part of the pipeline, '
                                  'skipping...'
                                  .format(model.get('name') or ''))

        return model_in_dag


def _load_jupyter_server_extension(app):
    """
    This function is called to configure the new content manager, there are a
    lot of quirks that jupytext maintainers had to solve to make it work so
    we base our implementation on theirs:
    https://github.com/mwouts/jupytext/blob/bc1b15935e096c280b6630f45e65c331f04f7d9c/jupytext/__init__.py#L19
    """
    if isinstance(app.contents_manager_class, PloomberContentsManager):
        app.log.info(
            "[Ploomber] NotebookApp.contents_manager_class "
            "is a subclass of PloomberContentsManager already - OK"
        )
        return

    # The server extension call is too late!
    # The contents manager was set at NotebookApp.init_configurables

    # Let's change the contents manager class
    app.log.info('[Ploomber] setting content manager '
                 'to PloomberContentsManager')
    app.contents_manager_class = PloomberContentsManager

    try:
        # And rerun selected init steps from https://github.com/jupyter/notebook/blob/
        # 132f27306522b32fa667a6b208034cb7a04025c9/notebook/notebookapp.py#L1634-L1638
        app.contents_manager = app.contents_manager_class(parent=app,
                                                          log=app.log)
        app.session_manager.contents_manager = app.contents_manager
        app.web_app.settings["contents_manager"] = app.contents_manager

    except DAGSpecInitializationError as e:
        app.log.error('[Ploomber] An error occured when trying to initialize '
                      'the pipeline. If you want cells to be injected, '
                      'fix the issue and restart "jupyter notebook"')
        raise
    except Exception:
        error = """[Ploomber] An error occured. Please
deactivate the server extension with "jupyter serverextension disable ploomber"
and configure the contents manager manually by adding
c.NotebookApp.contents_manager_class = "ploomber.jupyter.PloomberContentsManager"
to your .jupyter/jupyter_notebook_config.py file.
"""
        app.log.error(error)
        raise
