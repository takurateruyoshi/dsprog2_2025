import flet as ft


def main(page: ft.Page):
    counter = ft.Text("0", size=50, data=0)
    greeting = ft.Text("Hello world", size=50)
    greeting.value = "Hello world"

    def increment_click(e):
        counter.data += 1
        counter.value = str(counter.data)
        counter.update()

    def decrement_click(e):
        counter.data -= 1
        counter.value = str(counter.data)
        counter.update()

    page.add(
        ft.SafeArea(
            # Container Column 列　Row 行
            ft.Container(
                content = ft.Column(controls=[counter, greeting]),
                alignment=ft.alignment.center,
            ),
            expand=True,
        ),
        ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=increment_click),
        ft.FloatingActionButton(icon=ft.Icons.REMOVE, on_click=decrement_click),
    )
ft.app(main)
