from fractal_database.apps import FractalDatabaseConfig

async def test_database_test_setup():
    print('testing that the test setup worked')

    test = FractalDatabaseConfig(app_name="test name", app_module=None)

    test.ready()

    assert True
