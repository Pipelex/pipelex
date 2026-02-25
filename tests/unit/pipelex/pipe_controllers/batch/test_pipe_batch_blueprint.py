from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class TestPipeBatchBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeBatchBlueprint(
            description="lorem ipsum",
            inputs={"items": "Text[]"},
            output="Text[]",
            branch_pipe_code="process_item",
            input_list_name="items",
            input_item_name="item",
        )
        assert blueprint.pipe_dependencies == {"process_item"}

        blueprint = PipeBatchBlueprint(
            description="lorem ipsum",
            inputs={"data_list": "Number[]"},
            output="Number[]",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="data",
        )
        assert blueprint.pipe_dependencies == {"transform_data"}
